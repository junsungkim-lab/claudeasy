"""
Multi-provider sequential pipeline
- 각 에이전트가 다른 provider/model 사용 가능
- 이전 에이전트 출력(MD)을 컨텍스트로 누적해서 다음 에이전트에 전달
- Claude: CLI subprocess / OpenAI·Gemini: API 직접 호출
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, AsyncIterator
import httpx

# ── 에이전트 정의 ────────────────────────────────────────────────────────────

@dataclass
class Agent:
    role: str               # "PM", "Designer", "Dev", "QA" 등
    provider: str           # "claude" | "openai" | "gemini"
    model: str              # 실제 모델 ID
    system_prompt: str      # 역할 정의
    output_file: str        # 이 에이전트가 생성할 MD 파일명


# 기본 에이전트 세트 — 필요에 맞게 수정
DEFAULT_AGENTS: list[Agent] = [
    Agent(
        role="PM",
        provider="openai",
        model="gpt-4o",
        system_prompt="""You are an experienced Product Manager.
Write a clear PRD (Product Requirements Document) in Markdown.
Include: Overview, Goals, User Stories, Functional Requirements, Non-Functional Requirements, Out of Scope.
Output ONLY the markdown document, no extra commentary.""",
        output_file="PRD.md",
    ),
    Agent(
        role="Designer",
        provider="gemini",
        model="gemini-2.5-flash",
        system_prompt="""You are a senior UX/Product Designer.
Based on the PRD provided, write a DESIGN.md document.
Include: Information Architecture, User Flows, Screen Inventory, Component Library, Design Tokens, Accessibility notes.
Output ONLY the markdown document, no extra commentary.""",
        output_file="DESIGN.md",
    ),
    Agent(
        role="Dev",
        provider="claude",
        model="claude-sonnet-4-6",
        system_prompt="""You are a senior software engineer.
Based on the PRD and DESIGN docs provided, write a TECH_SPEC.md.
Include: Architecture, Data Models, API Endpoints, Key Algorithms, Dependencies, Dev Setup.
Output ONLY the markdown document, no extra commentary.""",
        output_file="TECH_SPEC.md",
    ),
    Agent(
        role="QA",
        provider="claude",
        model="claude-haiku-4-5-20251001",
        system_prompt="""You are a QA engineer.
Based on all documents provided, write a QA_REPORT.md.
Include: Test Plan, Test Cases (happy path + edge cases), Risk Assessment, Acceptance Criteria.
Output ONLY the markdown document, no extra commentary.""",
        output_file="QA_REPORT.md",
    ),
]


# ── Provider 구현 ────────────────────────────────────────────────────────────

async def run_claude(agent: Agent, prompt: str, on_chunk: Callable[[str], None] = None) -> str:
    """Claude CLI subprocess로 실행 (stream-json)"""
    args = [
        "claude", "-p",
        "--output-format", "stream-json",
        "--input-format", "stream-json",
        "--verbose",
        "--permission-mode", "bypassPermissions",
        "--model", agent.model,
        "--append-system-prompt", agent.system_prompt,
    ]

    input_payload = json.dumps({
        "type": "user",
        "message": {"role": "user", "content": prompt},
    })

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    proc.stdin.write(input_payload.encode())
    await proc.stdin.drain()
    proc.stdin.close()

    output = ""
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        try:
            ev = json.loads(line.decode().strip())
            if ev.get("type") == "assistant":
                for block in ev.get("message", {}).get("content", []):
                    if block.get("type") == "text":
                        chunk = block["text"]
                        output += chunk
                        if on_chunk:
                            on_chunk(chunk)
            elif ev.get("type") == "result" and ev.get("result"):
                if not output:
                    output = ev["result"]
        except json.JSONDecodeError:
            pass

    await proc.wait()
    return output


async def run_openai(agent: Agent, prompt: str, on_chunk: Callable[[str], None] = None) -> str:
    """OpenAI API streaming"""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 환경변수가 없습니다")

    output = ""
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST",
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": agent.model,
                "stream": True,
                "messages": [
                    {"role": "system", "content": agent.system_prompt},
                    {"role": "user", "content": prompt},
                ],
            },
        ) as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)["choices"][0]["delta"].get("content", "")
                    if chunk:
                        output += chunk
                        if on_chunk:
                            on_chunk(chunk)
                except (json.JSONDecodeError, KeyError):
                    pass
    return output


async def run_gemini(agent: Agent, prompt: str, on_chunk: Callable[[str], None] = None) -> str:
    """Google Gemini API streaming"""
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY 환경변수가 없습니다")

    output = ""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{agent.model}:streamGenerateContent?key={api_key}&alt=sse"
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST", url,
            headers={"Content-Type": "application/json"},
            json={
                "system_instruction": {"parts": [{"text": agent.system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            },
        ) as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                    chunk = data["candidates"][0]["content"]["parts"][0]["text"]
                    output += chunk
                    if on_chunk:
                        on_chunk(chunk)
                except (json.JSONDecodeError, KeyError):
                    pass
    return output


PROVIDER_MAP = {
    "claude": run_claude,
    "openai": run_openai,
    "gemini": run_gemini,
}


# ── Pipeline Runner ──────────────────────────────────────────────────────────

@dataclass
class StageResult:
    role: str
    provider: str
    model: str
    output: str
    output_file: str


async def run_pipeline(
    task: str,
    agents: list[Agent] = None,
    output_dir: Path = None,
    on_event: Callable[[dict], None] = None,  # 실시간 이벤트 콜백
) -> list[StageResult]:
    """
    순차 파이프라인 실행.
    각 에이전트 출력은 MD 파일로 저장되고, 다음 에이전트의 컨텍스트에 누적됨.
    """
    if agents is None:
        agents = DEFAULT_AGENTS
    if output_dir is None:
        output_dir = Path("./pipeline_output")
    output_dir.mkdir(parents=True, exist_ok=True)

    def emit(event: dict):
        if on_event:
            on_event(event)

    results: list[StageResult] = []

    for i, agent in enumerate(agents):
        emit({"type": "stage_start", "role": agent.role, "provider": agent.provider, "model": agent.model, "index": i})

        # 컨텍스트 빌드: 원본 태스크 + 이전 에이전트들의 MD 출력
        context_parts = [f"## 원본 태스크\n{task}"]
        for prev in results:
            context_parts.append(f"## {prev.role} 결과 ({prev.output_file})\n{prev.output}")
        prompt = "\n\n---\n\n".join(context_parts)

        # 스트리밍 청크를 실시간으로 전달
        def on_chunk(chunk: str, role=agent.role):
            emit({"type": "chunk", "role": role, "chunk": chunk})

        runner = PROVIDER_MAP.get(agent.provider)
        if runner is None:
            raise ValueError(f"알 수 없는 provider: {agent.provider}")

        output = await runner(agent, prompt, on_chunk=on_chunk)

        # MD 파일로 저장
        md_path = output_dir / agent.output_file
        md_path.write_text(output, encoding="utf-8")

        result = StageResult(
            role=agent.role,
            provider=agent.provider,
            model=agent.model,
            output=output,
            output_file=agent.output_file,
        )
        results.append(result)
        emit({"type": "stage_done", "role": agent.role, "output_file": str(md_path)})

    emit({"type": "pipeline_done", "stages": len(results)})
    return results
