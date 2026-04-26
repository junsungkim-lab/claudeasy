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
from core.design_systems import format_for_prompt as _design_systems_prompt
from core.design_systems import inject_into_prompt as _inject_design

HOME = Path.home()
CLAUDE_DIR = HOME / ".claude"
AGENTS_DIR = CLAUDE_DIR / "agents"
SKILLS_DIR = CLAUDE_DIR / "skills"
HARNESS_SKILL_PATH = Path(__file__).parent / "_harness_skill.md"
HARNESS_SKILL_URL = "https://raw.githubusercontent.com/revfactory/harness/main/skills/harness/SKILL.md"

AGENT_COLORS = ["#6366f1","#ec4899","#f59e0b","#10b981","#3b82f6","#8b5cf6","#ef4444"]


def _get_reserved_ports() -> list[int]:
    """현재 이 프로세스(claude-local)가 점유 중인 포트를 런타임에 감지."""
    import socket
    reserved = []
    # server.py가 사용하는 PORT 환경변수
    server_port = int(os.environ.get("PORT", 8100))
    reserved.append(server_port)
    # Vite dev 서버가 쓰는 포트도 추가 (보통 5173)
    for p in [5173, 5174]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", p)) == 0:
                reserved.append(p)
    return reserved


def parse_artifact(output: str, project_path: str = None) -> dict | None:
    """카드 output에서 ```artifact 블록을 파싱해 반환.
    없으면 출력 텍스트에서 실행 명령 패턴을 fallback 감지.
    """
    # 1순위: 명시적 artifact 블록
    match = re.search(r"```artifact\s*(\{.*?\})\s*```", output, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            artifact_type = data.get("type")
            if artifact_type not in ("server", "script"):
                return None
            return {
                "type": artifact_type,
                "run_command": data.get("run_command", ""),
                "port": data.get("port"),
                "cwd": data.get("cwd") or project_path,
            }
        except (json.JSONDecodeError, KeyError):
            pass

    # 포트 추출 헬퍼 — "port 8080", ":8080", "localhost:8080", "--port 8080" 형태 인식
    def _extract_port(text: str) -> int | None:
        m = re.search(r"(?:--port\s+|localhost:|:\s*)(\d{4,5})\b", text)
        if m:
            return int(m.group(1))
        m = re.search(r"\bport[=\s]+(\d{4,5})\b", text, re.IGNORECASE)
        if m:
            return int(m.group(1))
        return None

    # 2순위: Python 서버 (server.py / app.py / uvicorn / python -m uvicorn)
    py_server_match = re.search(
        r"(?:python3?\s+-m\s+uvicorn|uvicorn|python3?)\s+([\w./]+\.py(?:\s+--\S+)*(?:\s+main:\S+)?)",
        output
    )
    if py_server_match:
        cmd = py_server_match.group(0).strip().split("\n")[0]
        port = _extract_port(output)
        return {"type": "server", "run_command": cmd, "port": port, "cwd": project_path}

    # 3순위: Node/npm/pnpm/yarn/bun/vite/next 서버
    node_server_match = re.search(
        r"(?:npm run (?:dev|start|serve)|pnpm (?:dev|run dev|start)|yarn (?:dev|start)|"
        r"bun run (?:dev|start)|next dev|vite(?:\s+--\S+)*|node\s+[\w./]+\.(?:js|mjs|cjs))",
        output
    )
    if node_server_match:
        cmd = node_server_match.group(0).strip().split("\n")[0]
        port = _extract_port(output) or 3000
        return {"type": "server", "run_command": cmd, "port": port, "cwd": project_path}

    # 4순위: Python 웹 프레임워크 (flask / streamlit / gunicorn / hypercorn)
    py_web_match = re.search(
        r"(?:flask run|streamlit run\s+\S+|gunicorn\s+\S+|hypercorn\s+\S+|daphne\s+\S+)",
        output
    )
    if py_web_match:
        cmd = py_web_match.group(0).strip().split("\n")[0]
        port = _extract_port(output) or (8501 if "streamlit" in cmd else 5000)
        return {"type": "server", "run_command": cmd, "port": port, "cwd": project_path}

    # 5순위: Python 스크립트 (main.py / cli.py / run.py)
    script_match = re.search(
        r"(?:(?:\.venv/bin/)?python3?)\s+(main\.py|cli\.py|run\.py|script\.py)(?:\s+[^\n`]{0,80})?",
        output
    )
    if script_match:
        cmd = script_match.group(0).strip().split("\n")[0]
        return {"type": "script", "run_command": cmd, "port": None, "cwd": project_path}

    # 6순위: npm/bun/tsx/ts-node 스크립트
    ts_script_match = re.search(
        r"(?:tsx|ts-node|bun)\s+[\w./]+\.(?:ts|js)",
        output
    )
    if ts_script_match:
        cmd = ts_script_match.group(0).strip().split("\n")[0]
        return {"type": "script", "run_command": cmd, "port": None, "cwd": project_path}

    return None


def _build_port_rule() -> str:
    reserved = _get_reserved_ports()
    reserved_str = ", ".join(str(p) for p in sorted(reserved)) if reserved else "없음"
    return f"""
## Artifact Output (REQUIRED)
After completing all file writes, output an artifact JSON block:

```artifact
{{"type": "script", "run_command": "python main.py", "cwd": "/absolute/path/to/project"}}
```

Rules:
- type MUST be "script" (NOT "server", NOT "web")
- run_command: exact shell command to run the main script
- cwd: absolute directory path — MUST equal the board's shared project directory
- Do NOT create web servers, FastAPI apps, or Flask apps unless explicitly asked
- Do NOT use ports: {reserved_str}

## ⚠️ SINGLE PROJECT DIRECTORY (ABSOLUTE PRIORITY)
All tasks in this board share ONE project directory.
- The FIRST task picks the directory; ALL subsequent tasks use that EXACT same path.
- Integration/test tasks MUST NOT create a new sibling folder (e.g. *-test, *-v2, *-integration, *-beer-blog).
- artifact cwd MUST equal the shared project directory, never a sibling.

## ⚠️ AI 호출은 반드시 Claude CLI 사용 (ABSOLUTE PRIORITY)
- `anthropic` Python SDK, `import anthropic`, `Anthropic()` 클라이언트 사용 **금지**
- AI 텍스트 생성이 필요하면 Claude CLI subprocess로 호출할 것:

```python
import subprocess, sys

def call_claude(prompt: str) -> str:
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "text"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()
```

- `ANTHROPIC_API_KEY` 환경변수 불필요 → `.env.example`에 포함하지 말 것
- `anthropic`을 `requirements.txt`에 추가하지 말 것
"""


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
1. Generate agent definition files to ~/.claude/agents/{{name}}.md
   (IMPORTANT: agents are ALWAYS global — never create agent files inside the project directory)
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
    {{"title": "태스크 제목", "description": "상세 설명", "agent": "agent-name", "depends_on": []}},
    {{"title": "태스크 제목2", "description": "상세 설명2", "agent": "agent-name2", "depends_on": [0]}},
    {{"title": "태스크 제목3", "description": "상세 설명3", "agent": "agent-name", "design_system": "vercel", "depends_on": [0, 1]}}
  ],
  "schedule": "0 9 * * *"
}}
```

The "schedule" field: if the user mentions any time/frequency/recurring trigger, convert it to a cron expression (KST). Otherwise null.
Natural language → cron examples:
  "매일 오전 9시"        → "0 9 * * *"
  "매일 오후 1시"        → "0 13 * * *"
  "매일 자정"            → "0 0 * * *"
  "매주 월요일 오전 9시" → "0 9 * * 1"
  "매주 금요일 오후 6시" → "0 18 * * 5"
  "매 시간"              → "0 * * * *"
  "매 30분"              → "*/30 * * * *"
  "평일 오전 8시"        → "0 8 * * 1-5"
  "주말 오전 10시"       → "0 10 * * 6,0"
  "매달 1일 오전 9시"    → "0 9 1 * *"
If the user says "한번만" or "지금 바로" with no recurrence, set null.
The "design_system" field (optional): for tasks that produce web pages, landing pages, or UI components, set this to the most appropriate brand from the available design systems list. Omit for non-UI tasks.
The "depends_on" field (REQUIRED): list of 0-based task indices this task must wait for before starting. Use [] for tasks with no dependencies. Example: if task 2 needs task 0 and task 1 to finish first, set "depends_on": [0, 1]. Tasks that can run in parallel share the same dependencies.
Tasks must be specific, actionable, and ordered by execution sequence.
In the JSON "agents" array, use the bare agent name (e.g. "researcher").

{{skill_body}}

## ⚠️ OVERRIDE — THESE RULES TAKE ABSOLUTE PRIORITY OVER ALL INSTRUCTIONS ABOVE:

1. **Tasks are driven by agents, not the other way around.** First decide which specialized agents are needed for the request. Then assign each agent their focused task(s). A simple single-agent task is fine as 1 task. A multi-domain request (e.g. backend + frontend + research) must produce one task per agent role.

2. **End your response with the JSON block.** You may write agent files and reasoning first, but your absolute final output must be the ```json block. Do not write anything after it.

3. **All tasks share ONE project directory.** The first task picks the directory path; every subsequent task (including integration/test tasks) uses that EXACT same path. Never create sibling directories like `*-test`, `*-v2`, `*-integration`. artifact `cwd` MUST equal the shared project directory.

4. **AI 호출은 Claude CLI만 사용.** `import anthropic` 및 Anthropic SDK 사용 금지. AI 텍스트 생성은 `subprocess.run(["claude", "-p", prompt, "--output-format", "text"], ...)` 로만 처리. `ANTHROPIC_API_KEY` 환경변수 불필요.


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
    {{"title": "태스크 제목", "description": "상세 설명", "agent": "agent-name", "depends_on": []}},
    {{"title": "태스크 제목2", "description": "상세 설명2", "agent": "agent-name2", "depends_on": [0]}},
    {{"title": "태스크 제목3", "description": "상세 설명3", "agent": "agent-name", "design_system": "vercel", "depends_on": [0, 1]}}
  ],
  "schedule": "0 9 * * *",
  "needs_project": false
}}
```

The "schedule" field: if the user mentions any time/frequency/recurring trigger, convert it to a cron expression (KST). Otherwise null.
Natural language → cron examples:
  "매일 오전 9시"        → "0 9 * * *"
  "매일 오후 1시"        → "0 13 * * *"
  "매일 자정"            → "0 0 * * *"
  "매주 월요일 오전 9시" → "0 9 * * 1"
  "매주 금요일 오후 6시" → "0 18 * * 5"
  "매 시간"              → "0 * * * *"
  "매 30분"              → "*/30 * * * *"
  "평일 오전 8시"        → "0 8 * * 1-5"
  "주말 오전 10시"       → "0 10 * * 6,0"
  "매달 1일 오전 9시"    → "0 9 1 * *"
If the user says "한번만" or "지금 바로" with no recurrence, set null.
"needs_project": true if tasks involve creating/modifying source code files or a software project, false for research/analysis/content only.
The "design_system" field (optional): for tasks that produce web pages, landing pages, or UI components, set this to the most appropriate brand from the available design systems list. Omit for non-UI tasks.
The "depends_on" field (REQUIRED): list of 0-based task indices this task must wait for before starting. Use [] for tasks with no dependencies. Example: if task 2 needs task 0 and task 1 to finish first, set "depends_on": [0, 1]. Tasks that can run in parallel share the same dependencies.
Tasks must be specific, actionable, and ordered by execution sequence.
In the JSON "agents" array, use only the bare agent name WITHOUT the prefix (e.g. "researcher", not "cllocal__researcher").

{skill_body}

## ⚠️ OVERRIDE — THESE RULES TAKE ABSOLUTE PRIORITY OVER ALL INSTRUCTIONS ABOVE:

1. **Tasks are driven by agents, not the other way around.** First decide which specialized agents are needed for the request. Then assign each agent their focused task(s). A simple single-agent task is fine as 1 task. A multi-domain request (e.g. backend + frontend + research) must produce one task per agent role.

2. **End your response with the JSON block.** You may write agent files and reasoning first, but your absolute final output must be the ```json block. Do not write anything after it.

3. **All tasks share ONE project directory.** The first task picks the directory path; every subsequent task (including integration/test tasks) uses that EXACT same path. Never create sibling directories like `*-test`, `*-v2`, `*-integration`. artifact `cwd` MUST equal the shared project directory.

4. **AI 호출은 Claude CLI만 사용.** `import anthropic` 및 Anthropic SDK 사용 금지. AI 텍스트 생성은 `subprocess.run(["claude", "-p", prompt, "--output-format", "text"], ...)` 로만 처리. `ANTHROPIC_API_KEY` 환경변수 불필요.


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

HARNESS_CLASSIFY_SYSTEM = """You are a request classifier for an AI automation platform called claude-local.

Your job: analyze the user's request and classify it into one of three kinds, then output ONLY a JSON object.

## Classification Rules

**automation**: The user wants a RECURRING, scheduled task that runs repeatedly at a fixed time.
- Keywords: 매일/매주/매시간/N분마다/자동으로/자동화/스케줄/주기적으로/정기적으로
- Action verbs: 실행/수집/발송/포스팅/업로드/모니터링/요약/정리
- Example: "매일 9시에 경제뉴스 요약해서 블로그에 올려줘"
- Example: "주 3회 인스타그램 포스팅 자동화해줘"

**build**: The user wants a ONE-TIME development artifact (app, dashboard, tool, website).
- Keywords: 만들어줘/개발해줘/구현해줘/대시보드/페이지/UI/서비스/앱/시스템
- Example: "블로그 관리자 대시보드 만들어줘"
- Example: "상품 재고 관리 시스템 구현해줘"

**needs_clarification**: The request is too vague to classify or missing critical info.
- Missing 2+ of: [platform/account, trigger timing, output destination, input source, result format]
- Example: "마케팅 자동화해줘" (what platform? what to automate? when?)
- Example: "SNS 관리해줘" (which platform? what actions? how often?)

## Output Schema

For **needs_clarification**:
```json
{
  "kind": "needs_clarification",
  "summary": "한 줄 요약",
  "questions": [
    {"id": "q1", "question": "어떤 플랫폼에 포스팅할까요? (네이버 블로그/티스토리/인스타그램 등)"},
    {"id": "q2", "question": "얼마나 자주 실행할까요? (매일/매주/특정 시간)"},
    {"id": "q3", "question": "콘텐츠 소재는 어디서 가져올까요? (웹 검색/직접 입력/특정 사이트)"}
  ]
}
```

For **automation**:
```json
{
  "kind": "automation",
  "summary": "한 줄 요약",
  "automation": {
    "agent_prompt": "너는 [역할] 에이전트야. tools/ 디렉토리의 스크립트를 Bash로 호출할 수 있어. [구체적인 매 실행 시 할 일]",
    "allowed_tools": ["Bash", "Read", "Write"],
    "schedule": "0 9 * * *",
    "tool_agents": [
      {"file": "tools/fetch_content.py", "task": "웹에서 콘텐츠를 수집해 JSON으로 반환하는 독립 실행 Python 스크립트"},
      {"file": "tools/post_to_platform.py", "task": "수집된 콘텐츠를 플랫폼에 게시하는 독립 실행 Python 스크립트"}
    ],
    "env_vars": [
      {"key": "PLATFORM_ID", "description": "플랫폼 로그인 ID"},
      {"key": "PLATFORM_PW", "description": "플랫폼 로그인 비밀번호"}
    ],
    "notify_channel": "telegram"
  }
}
```

For **build**: (keep existing agents+tasks format)
```json
{
  "kind": "build",
  "summary": "한 줄 요약",
  "agents": [...existing format...],
  "tasks": [...existing format...],
  "schedule": null
}
```

Output ONLY the JSON. No explanation, no markdown fences.
"""

HARNESS_TOOL_DEV_SYSTEM = """You are a Python tool developer for an AI automation platform.

Your task: create a single, reusable Python module that can be called as a standalone script.

## Rules (STRICT)
- NO web servers, NO FastAPI, NO Flask, NO HTTP endpoints
- The script MUST be runnable as: `python tools/filename.py`
- Use `os.environ.get('KEY')` for all sensitive values (API keys, passwords, etc.)
- Create `.env.example` listing all required env keys (values blank or placeholder)
- Add all dependencies to `requirements.txt` (one per line)
- Print progress to stdout, errors to stderr
- Exit with code 0 on success, non-zero on failure
- Keep it simple: one file, one purpose

## ⚠️ AI 호출 규칙 (ABSOLUTE PRIORITY)
- `anthropic` SDK, `import anthropic`, `Anthropic()` 클라이언트 사용 **금지**
- AI 텍스트 생성은 Claude CLI subprocess로만 호출:

```python
import subprocess, sys

def call_claude(prompt: str) -> str:
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "text"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()
```

- `ANTHROPIC_API_KEY` 불필요 → `.env.example`과 `requirements.txt`에 포함하지 말 것

## Output format
Write the Python file, then .env.example, then requirements.txt entries.
After writing all files, output the artifact block:

```artifact
{"type": "script", "run_command": "python tools/FILENAME.py", "cwd": "/path/to/tool_dir"}
```
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
    # 1순위: ```json 펜스
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 2순위: 중괄호 균형 기반 추출 — nested JSON도 올바르게 처리
    # "tasks" 키를 포함하는 가장 큰 객체를 찾는다
    best = None
    i = 0
    while i < len(text):
        if text[i] == '{':
            depth = 0
            for j in range(i, len(text)):
                if text[j] == '{':
                    depth += 1
                elif text[j] == '}':
                    depth -= 1
                    if depth == 0:
                        candidate = text[i:j + 1]
                        if '"tasks"' in candidate:
                            try:
                                parsed = json.loads(candidate)
                                # 더 많은 tasks를 포함한 것을 우선
                                if best is None or len(candidate) > len(best[0]):
                                    best = (candidate, parsed)
                            except json.JSONDecodeError:
                                pass
                        break
        i += 1

    if best:
        return best[1]
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
        stderr=asyncio.subprocess.PIPE,  # M-2: DEVNULL → PIPE로 변경해 에러 진단 보존
        cwd=str(cwd or HOME),
        limit=2**24,  # 16MB — stream-json 한 줄이 64KB 기본 한도를 넘을 때 방지
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

    # M-2: stderr 캡처 & 로깅
    try:
        stderr_data = await asyncio.wait_for(proc.stderr.read(), timeout=2)
        if stderr_data and proc.returncode != 0:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "[_run_claude] returncode=%d stderr=%s",
                proc.returncode,
                stderr_data[:500].decode(errors="replace"),
            )
    except asyncio.TimeoutError:
        pass

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
    system += _build_port_rule()
    system += "\n\n" + _design_systems_prompt()

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

    # 질문 감지 → 오케스트레이터 자동 답변 후 재시도 (1회)
    parsed = _parse_harness_json(output)
    if not parsed.get("tasks") and has_unanswered_questions(output):
        on_event({"type": "status", "text": "🤖 하네스 질문 자동 답변 중..."})
        answers = await generate_auto_answers(
            agent_output=output,
            card_title="",
            board_context=user_request,
            project_path=project_path,
        )
        retry_prompt = (
            full_prompt
            + "\n\n[오케스트레이터 자동 답변]\n"
            + answers
            + "\n\n위 답변을 바탕으로 에이전트 팀과 태스크를 구성하고 JSON을 출력하세요."
        )
        output, session_id, _ = await _run_claude(
            prompt=retry_prompt,
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
    design_system: str = None,
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
    system += _build_port_rule()
    if design_system:
        system = _inject_design(design_system, system)

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
