"""
Harness 생성 + 태스크 추출 + 카드별 에이전트 실행

에이전트 파일 위치 규칙:
  - project_path 있음 → {project_path}/.claude/agents/{name}.md
  - project_path 없음 → ~/.claude/agents/cllocal__{name}.md
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Callable

import httpx

import agents_registry

HOME = Path.home()
CLAUDE_DIR = HOME / ".claude"
AGENTS_DIR = CLAUDE_DIR / "agents"
SKILLS_DIR = CLAUDE_DIR / "skills"
HARNESS_SKILL_PATH = Path(__file__).parent / "_harness_skill.md"
HARNESS_SKILL_URL = "https://raw.githubusercontent.com/revfactory/harness/main/skills/harness/SKILL.md"

AGENT_COLORS = ["#6366f1","#ec4899","#f59e0b","#10b981","#3b82f6","#8b5cf6","#ef4444"]

# ── 에이전트 파일 경로 ────────────────────────────────────────────────────────

def get_agents_dir(project_path: str = None) -> Path:
    """에이전트 파일이 저장될 디렉토리 반환.
    프로젝트 있음 → {project_path}/.claude/agents/
    없음         → ~/.claude/agents/
    """
    if project_path:
        return Path(project_path) / ".claude" / "agents"
    return AGENTS_DIR


def get_agent_file(agent_name: str, project_path: str = None) -> Path:
    """에이전트 .md 파일 경로 반환."""
    if project_path:
        return get_agents_dir(project_path) / f"{agent_name}.md"
    return AGENTS_DIR / f"cllocal__{agent_name}.md"


def get_skill_dir(skill_name: str, project_path: str = None) -> Path:
    """스킬 디렉토리 경로 반환."""
    if project_path:
        return Path(project_path) / ".claude" / "skills" / skill_name
    return SKILLS_DIR / f"cllocal__{skill_name}"


def agents_exist_on_disk(agent_names: list[str], project_path: str = None) -> bool:
    """모든 에이전트 .md 파일이 이미 존재하는지 확인."""
    return bool(agent_names) and all(
        get_agent_file(n, project_path).exists() for n in agent_names
    )


def get_agent_prefix(project_path: str = None) -> str:
    """하위 호환용 — HARNESS_SYSTEM 프롬프트의 {prefix} 자리에 쓰임."""
    if not project_path:
        return "cllocal__"
    # 프로젝트 있으면 prefix 없이 순수 이름 사용
    return ""


# ── Harness 시스템 프롬프트 ──────────────────────────────────────────────────

HARNESS_SYSTEM_PROJECT = """You are the Harness Agent Team & Skill Architect.

Analyze the user's request and:
1. Generate agent definition files to {project_agents_dir}/{{name}}.md
   (e.g. {project_agents_dir}/researcher.md)
2. Generate skill files to {project_skills_dir}/{{name}}/SKILL.md
3. Generate orchestrator to {project_skills_dir}/orchestrator/SKILL.md
4. Use absolute paths.

After generating files, output EXACTLY this JSON block (nothing else after it):

```json
{{
  "agents": [
    {{"name": "agent-name", "role": "역할 설명"}}
  ],
  "tasks": [
    {{"title": "태스크 제목", "description": "상세 설명", "agent": "agent-name"}},
    {{"title": "태스크 제목2", "description": "상세 설명2", "agent": "agent-name2"}}
  ],
  "schedule": "0 9 * * *"
}}
```

The "schedule" field: extract cron expression if user mentions time/frequency, else null.
Tasks must be specific, actionable, and ordered by execution sequence.
In the JSON "agents" array, use the bare agent name (e.g. "researcher").

{{skill_body}}
"""

HARNESS_SYSTEM_GLOBAL = """You are the Harness Agent Team & Skill Architect.

Analyze the user's request. First, determine if the tasks require creating or modifying code/files in a project directory (needs_project=true), or if it's purely research/analysis/content generation with no file output (needs_project=false).

If needs_project=true, DO NOT generate any agent/skill files yet — just output the JSON.
If needs_project=false, proceed to:
1. Generate agent definition files to ~/.claude/agents/cllocal__{{name}}.md
   (IMPORTANT: the filename MUST start with "cllocal__" — e.g. cllocal__researcher.md)
2. Generate skill files to ~/.claude/skills/cllocal__{{name}}/SKILL.md
3. Generate orchestrator to ~/.claude/skills/cllocal__orchestrator/SKILL.md
4. Use absolute paths starting with ~/

After generating files (or immediately if needs_project=true), output EXACTLY this JSON block (nothing else after it):

```json
{{
  "agents": [
    {{"name": "agent-name", "role": "역할 설명"}}
  ],
  "tasks": [
    {{"title": "태스크 제목", "description": "상세 설명", "agent": "agent-name"}},
    {{"title": "태스크 제목2", "description": "상세 설명2", "agent": "agent-name2"}}
  ],
  "schedule": "0 9 * * *",
  "needs_project": false
}}
```

The "schedule" field: extract cron expression if user mentions time/frequency, else null.
"needs_project": true if tasks involve creating/modifying source code files or a software project, false for research/analysis/content only.
Tasks must be specific, actionable, and ordered by execution sequence.
In the JSON "agents" array, use only the bare agent name WITHOUT the prefix (e.g. "researcher", not "cllocal__researcher").

{skill_body}
"""

PROJECT_CONTEXT_HEADER = """
## 🗂️ 프로젝트 컨텍스트

현재 연결된 프로젝트: `{project_path}`

아래는 이 프로젝트의 CLAUDE.md (가이드라인):
---
{claude_md}
---

위 프로젝트 가이드라인을 반드시 준수하여 에이전트 팀과 태스크를 구성하세요.
특히 사용 가능한 명령어, 아키텍처 규칙, 코딩 규칙을 태스크 설명에 반영하세요.
"""

MEMORY_HEADER = """
## 🧠 프로젝트 장기 기억 (MEMORY.md)

이전 작업에서 축적된 핵심 지식입니다. 새 태스크 수행 시 참고하세요:
---
{memory}
---
"""


def load_project_context(project_path: str) -> str:
    if not project_path:
        return ""
    p = Path(project_path)

    # CLAUDE.md
    claude_md = p / "CLAUDE.md"
    if claude_md.exists():
        content = claude_md.read_text(encoding="utf-8", errors="ignore")
        if len(content) > 4000:
            content = content[:4000] + "\n...(이하 생략)"
        result = PROJECT_CONTEXT_HEADER.format(project_path=project_path, claude_md=content)
    else:
        result = f"\n## 🗂️ 프로젝트: `{project_path}`\n(CLAUDE.md 없음)\n"

    # MEMORY.md — 있으면 읽어서 추가
    memory_md = p / "MEMORY.md"
    if memory_md.exists():
        memory = memory_md.read_text(encoding="utf-8", errors="ignore")
        if len(memory) > 3000:
            memory = memory[-3000:]  # 최신 내용 우선 (끝부분)
        result += MEMORY_HEADER.format(memory=memory)

    return result


async def update_project_memory(
    project_path: str,
    card_title: str,
    output: str,
) -> None:
    """카드 완료 후 핵심 내용을 MEMORY.md에 날짜별로 추가."""
    if not project_path or not output or not output.strip():
        return

    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")

    # Claude로 핵심 요약 생성
    summary_chunks: list[str] = []
    prompt = f"""다음 작업 결과에서 **이 프로젝트에 지속적으로 유용한 핵심 정보**만 3~5개 bullet로 요약하세요.
구체적인 파일 경로, 명령어, 결정 사항, 발견한 패턴 등 실용적인 내용 위주로 작성하세요.
날짜나 제목은 포함하지 마세요 (자동으로 추가됩니다).

## 작업 제목
{card_title}

## 작업 결과
{output[:3000]}

bullet 포인트만 출력하세요 (- 로 시작)."""

    try:
        await _run_claude(
            prompt=prompt,
            system_prompt="You are a memory summarizer. Extract only durable, reusable insights from task outputs. Reply in Korean. Output bullet points only.",
            on_chunk=lambda c: summary_chunks.append(c),
        )  # returns 3-tuple but we only need side-effect (on_chunk)
        summary = "".join(summary_chunks).strip()
        if not summary:
            return
    except Exception:
        return

    # MEMORY.md에 날짜별로 추가
    memory_md = Path(project_path) / "MEMORY.md"
    existing = memory_md.read_text(encoding="utf-8") if memory_md.exists() else "# 프로젝트 장기 기억\n\n"

    entry = f"\n## {today} — {card_title}\n{summary}\n"
    memory_md.write_text(existing + entry, encoding="utf-8")


# ── 유틸 ────────────────────────────────────────────────────────────────────

async def fetch_harness_skill() -> str:
    if HARNESS_SKILL_PATH.exists():
        return HARNESS_SKILL_PATH.read_text()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(HARNESS_SKILL_URL)
        content = r.text
        HARNESS_SKILL_PATH.write_text(content)
        return content


async def tavily_search(query: str) -> str:
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return ""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "max_results": 5, "search_depth": "basic"},
        )
        results = r.json().get("results", [])
        if not results:
            return ""
        lines = ["## 최신 참고 정보"]
        for item in results:
            lines.append(f"- **{item.get('title','')}**: {item.get('content','')[:200]}")
        return "\n".join(lines)


def _parse_harness_json(text: str) -> dict:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    matches = re.findall(r"\{[^{}]*\"tasks\"[^{}]*\[.*?\][^{}]*\}", text, re.DOTALL)
    if matches:
        try:
            return json.loads(matches[-1])
        except json.JSONDecodeError:
            pass
    return {}


# ── Claude CLI 실행 ──────────────────────────────────────────────────────────

async def _run_claude(
    prompt: str,
    system_prompt: str,
    on_chunk: Callable[[str], None] = None,
    cwd: Path = None,
    session_id: str = None,
    on_session_id: Callable[[str], None] = None,
) -> tuple[str, str]:
    args = [
        "claude", "-p",
        "--output-format", "stream-json",
        "--input-format", "stream-json",
        "--verbose",
        "--permission-mode", "bypassPermissions",
        "--append-system-prompt", system_prompt,
    ]
    if session_id:
        args += ["--resume", session_id]

    input_payload = json.dumps({
        "type": "user",
        "message": {"role": "user", "content": prompt},
    })

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        cwd=str(cwd or HOME),
    )
    proc.stdin.write(input_payload.encode())
    await proc.stdin.drain()
    proc.stdin.close()

    output = ""
    captured_session_id = session_id
    session_error = False

    async for line in proc.stdout:
        try:
            ev = json.loads(line.decode().strip())
            if ev.get("type") == "system" and ev.get("session_id"):
                captured_session_id = ev["session_id"]
                if on_session_id:
                    on_session_id(captured_session_id)
            elif ev.get("type") == "assistant":
                for block in ev.get("message", {}).get("content", []):
                    if block.get("type") == "text":
                        chunk = block["text"]
                        output += chunk
                        if on_chunk:
                            on_chunk(chunk)
            elif ev.get("type") == "result":
                if ev.get("is_error") and not output:
                    # --resume 실패 (세션 만료/없음) — 새 세션으로 재시도
                    session_error = True
                elif ev.get("result") and not output:
                    output = ev["result"]
        except json.JSONDecodeError:
            pass

    await proc.wait()

    return output, captured_session_id, session_error


# ── Harness 생성 ─────────────────────────────────────────────────────────────

async def generate_harness(
    user_request: str,
    on_event: Callable[[dict], None],
    use_tavily: bool = False,
    tavily_query: str = "",
    project_path: str = None,
    existing_agent_names: list[str] = None,  # DB에 이미 있는 에이전트 이름 목록
) -> dict:
    """
    Harness 생성.

    재사용 로직:
    - existing_agent_names 가 있고 해당 .md 파일이 모두 디스크에 존재하면
      Claude 호출 없이 즉시 반환 (기존 에이전트 재사용).
    - 그렇지 않으면 Claude로 에이전트/스킬 파일 생성.
    """
    # ── 재사용 판단 ──────────────────────────────────────────────────────────
    if existing_agent_names and agents_exist_on_disk(existing_agent_names, project_path):
        loc = f"{project_path}/.claude/agents" if project_path else "~/.claude/agents"
        on_event({"type": "status", "text": f"♻️  기존 에이전트 재사용 중 ({loc})..."})
        return {"agents": None, "tasks": None, "schedule": None, "session_id": None, "reused": True}

    # ── 신규 생성 ────────────────────────────────────────────────────────────
    context = ""
    if use_tavily:
        on_event({"type": "status", "text": "🔍 최신 정보 검색 중..."})
        context = await tavily_search(tavily_query or user_request)

    agents_dir = get_agents_dir(project_path)
    agents_dir.mkdir(parents=True, exist_ok=True)

    loc_label = str(agents_dir).replace(str(HOME), "~")
    on_event({"type": "status", "text": f"🏗️  에이전트 팀 구성 중 ({loc_label})..."})

    skill_body = await fetch_harness_skill()
    available_agents_block = agents_registry.format_for_prompt()

    if project_path:
        skills_dir = get_skill_dir("", project_path).parent
        skills_dir.mkdir(parents=True, exist_ok=True)
        system = HARNESS_SYSTEM_PROJECT.format(
            project_agents_dir=str(agents_dir),
            project_skills_dir=str(skills_dir),
        ).replace("{skill_body}", skill_body + available_agents_block)
    else:
        AGENTS_DIR.mkdir(parents=True, exist_ok=True)
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        system = HARNESS_SYSTEM_GLOBAL.format(skill_body=skill_body + available_agents_block)

    project_context = load_project_context(project_path)

    full_prompt = user_request
    if project_context:
        full_prompt = project_context + "\n\n## 요청\n" + user_request
    if context:
        full_prompt = context + "\n\n---\n\n" + full_prompt

    cwd = Path(project_path) if project_path else HOME

    output, session_id, _ = await _run_claude(
        prompt=full_prompt,
        system_prompt=system,
        on_chunk=lambda c: on_event({"type": "harness_chunk", "text": c}),
        on_session_id=lambda sid: on_event({"type": "session_id", "session_id": sid}),
        cwd=cwd,
    )

    parsed = _parse_harness_json(output)
    parsed["session_id"] = session_id
    parsed["reused"] = False
    return parsed


# ── 카드 실행 ────────────────────────────────────────────────────────────────

async def run_card(
    card_title: str,
    card_description: str,
    agent_name: str,
    context: str,
    on_chunk: Callable[[str], None],
    session_id: str = None,
    on_session_id: Callable[[str], None] = None,
    project_path: str = None,
) -> tuple[str, str]:
    """
    단일 카드(태스크) 실행.

    에이전트 파일 탐색 순서:
      1. project_path 있음 → {project_path}/.claude/agents/{name}.md
         없음             → ~/.claude/agents/cllocal__{name}.md
      2. harness-100 라이브러리 (agents_registry)
      3. 전역 ~/.claude/agents/{name}.md
    """
    orchestrator_path = get_skill_dir("orchestrator", project_path) / "SKILL.md"
    agent_path = get_agent_file(agent_name, project_path)

    system_parts = []

    # 1순위: 프로젝트 내부 or cllocal 파일
    if agent_path.exists():
        system_parts.append(agent_path.read_text())
    else:
        # 2순위: harness-100 라이브러리
        lib_content = agents_registry.get_agent_content(agent_name)
        if lib_content:
            system_parts.append(lib_content)
        else:
            # 3순위: 전역 ~/.claude/agents/{name}.md
            global_path = AGENTS_DIR / f"{agent_name}.md"
            if global_path.exists():
                system_parts.append(global_path.read_text())

    if orchestrator_path.exists():
        system_parts.append(orchestrator_path.read_text())

    project_context = load_project_context(project_path)
    if project_context:
        system_parts.append(project_context)

    system = "\n\n---\n\n".join(system_parts) if system_parts else \
        f"You are {agent_name}. Complete the assigned task."

    cwd = Path(project_path) if project_path else HOME

    full_prompt = f"""## 태스크
{card_title}

## 상세
{card_description}

## 프로젝트 컨텍스트
{context}

위 태스크를 완료하세요."""

    short_prompt = f"## 다음 태스크\n{card_title}\n\n{card_description}"

    prompt = short_prompt if session_id else full_prompt

    output, new_session_id, session_error = await _run_claude(
        prompt=prompt,
        system_prompt=system,
        on_chunk=on_chunk,
        on_session_id=on_session_id,
        cwd=cwd,
        session_id=session_id,
    )

    # 세션 만료/오류 → 풀 프롬프트로 새 세션 재시도
    if session_error:
        output, new_session_id, _ = await _run_claude(
            prompt=full_prompt,
            system_prompt=system,
            on_chunk=on_chunk,
            on_session_id=on_session_id,
            cwd=cwd,
            session_id=None,
        )

    return output, new_session_id


# ── 자동 답변 오케스트레이터 ──────────────────────────────────────────────────

def has_unanswered_questions(output: str) -> bool:
    """에이전트 output에 미답변 질문이 포함됐는지 휴리스틱 감지."""
    if not output or len(output) < 50:
        return False

    # 질문 패턴: ?로 끝나는 줄 2개 이상, 또는 A)/B)/C) 선택지, 또는 번호 질문 목록
    question_lines = [l for l in output.splitlines() if l.strip().endswith("?")]
    has_lettered_options = bool(
        re.search(r"^\s*[\*\-]?\s*\*?\*?[ABC]\)", output, re.MULTILINE) or
        re.search(r"\*\*[ABC]\)\*\*", output)
    )
    has_numbered_questions = bool(
        re.search(r"^\s*\d+\.\s.*\?", output, re.MULTILINE)
    )
    has_confirm_phrase = any(p in output for p in [
        "확인하고 싶", "어떻게 하실", "어떤 방향", "알려주시면",
        "말씀해 주시면", "결정해 주세요", "선택해 주세요",
    ])

    return (
        len(question_lines) >= 2
        or has_lettered_options
        or has_numbered_questions
        or has_confirm_phrase
    )


async def generate_auto_answers(
    agent_output: str,
    card_title: str,
    board_context: str,
    project_path: str | None,
) -> str:
    """에이전트가 던진 질문들에 대해 프로젝트 컨텍스트 기반으로 자동 답변 생성."""
    memory = load_project_context(project_path) or ""
    memory_section = ("## 프로젝트 메모리\n" + memory) if memory else ""

    prompt = (
        "다음은 AI 에이전트가 태스크를 진행하다가 사용자에게 확인을 요청한 내용입니다.\n"
        "프로젝트 컨텍스트를 바탕으로 각 질문에 구체적으로 답하고, 에이전트가 바로 작업을 이어갈 수 있게 해주세요.\n\n"
        f"## 태스크\n{card_title}\n\n"
        f"## 보드 컨텍스트\n{board_context}\n\n"
        f"{memory_section}\n\n"
        f"## 에이전트 출력 (질문 포함)\n{agent_output}\n\n"
        "---\n\n"
        "위 질문/선택지에 대한 답변을 작성하세요.\n"
        "- 각 항목별로 명확하게 선택/결정해 주세요\n"
        "- 근거를 한 줄씩 붙여주세요\n"
        "- 에이전트가 이 답변만 보고 바로 작업할 수 있을 정도로 구체적으로 작성하세요"
    )

    system = (
        "You are a project coordinator. "
        "Based on the project context, make concrete decisions for the agent's questions. "
        "Reply in Korean. Be decisive and specific."
    )

    chunks: list[str] = []
    await _run_claude(prompt=prompt, system_prompt=system, on_chunk=lambda c: chunks.append(c))
    return "".join(chunks).strip()
