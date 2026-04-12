"""
harness-100 서브모듈 에이전트 레지스트리

구조:
  harness-100/ko/{NN}-{harness-name}/.claude/agents/{agent-name}.md

각 .md 파일 frontmatter:
  ---
  name: agent-name
  description: "설명"
  ---

제공 기능:
  - 전체 에이전트 인덱스 빌드 (name → {path, description, harness})
  - harness 프롬프트용 에이전트 목록 문자열 생성
  - agent_name으로 .md 내용 조회
  - 서브모듈 git pull (일일 동기화)
"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SUBMODULE_DIR = Path(__file__).parent / "harness-100"
PREFERRED_LANG = "ko"   # 한국어 우선, 없으면 en fallback


# ── frontmatter 파서 ──────────────────────────────────────────────────────────

def _parse_frontmatter(md_path: Path) -> dict:
    """YAML frontmatter에서 name, description 추출."""
    try:
        text = md_path.read_text(encoding="utf-8", errors="ignore")
        match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not match:
            return {}
        fm = {}
        for line in match.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                fm[k.strip()] = v.strip().strip('"\'')
        return fm
    except Exception:
        return {}


# ── 인덱스 빌드 ───────────────────────────────────────────────────────────────

def build_index() -> dict[str, dict]:
    """
    반환: {agent_name: {path, description, harness, lang}}
    같은 이름이 여러 harness에 있으면 번호가 작은(앞선) harness 우선.
    """
    if not SUBMODULE_DIR.exists():
        logger.warning("[registry] harness-100 서브모듈 없음: %s", SUBMODULE_DIR)
        return {}

    lang_dir = SUBMODULE_DIR / PREFERRED_LANG
    if not lang_dir.exists():
        lang_dir = SUBMODULE_DIR / "en"

    index: dict[str, dict] = {}

    for harness_dir in sorted(lang_dir.iterdir()):
        if not harness_dir.is_dir():
            continue
        agents_dir = harness_dir / ".claude" / "agents"
        if not agents_dir.exists():
            continue
        for agent_file in sorted(agents_dir.glob("*.md")):
            fm = _parse_frontmatter(agent_file)
            name = fm.get("name") or agent_file.stem
            desc = fm.get("description", "")
            if name not in index:   # 번호 앞선 harness 우선
                index[name] = {
                    "path":        agent_file,
                    "description": desc,
                    "harness":     harness_dir.name,
                    "lang":        lang_dir.name,
                }

    logger.info("[registry] 인덱스 빌드 완료: %d개 에이전트", len(index))
    return index


# ── 런타임 캐시 ───────────────────────────────────────────────────────────────

_index: dict[str, dict] = {}


def get_index() -> dict[str, dict]:
    global _index
    if not _index:
        _index = build_index()
    return _index


def refresh_index():
    global _index
    _index = build_index()
    return _index


# ── 조회 API ──────────────────────────────────────────────────────────────────

def get_agent_content(agent_name: str) -> Optional[str]:
    """에이전트 이름으로 .md 내용 반환. 없으면 None."""
    entry = get_index().get(agent_name)
    if entry and entry["path"].exists():
        return entry["path"].read_text(encoding="utf-8", errors="ignore")
    return None


def search_agents(query: str, limit: int = 10) -> list[dict]:
    """description/name에서 키워드 검색."""
    q = query.lower()
    results = []
    for name, info in get_index().items():
        score = 0
        if q in name.lower():
            score += 2
        if q in info["description"].lower():
            score += 1
        if score:
            results.append({"name": name, **info, "score": score})
    results.sort(key=lambda x: -x["score"])
    return results[:limit]


def format_for_prompt(max_agents: int = 80) -> str:
    """
    harness 시스템 프롬프트에 주입할 에이전트 목록.
    Claude가 이 목록에서 골라 쓰도록 유도.
    """
    idx = get_index()
    if not idx:
        return ""

    lines = [
        f"\n## ♻️ 사용 가능한 사전 제작 에이전트 ({len(idx)}개 중 상위 {min(len(idx), max_agents)}개)",
        "아래 에이전트가 이미 harness-100 라이브러리에 존재합니다.",
        "**적합한 에이전트가 있으면 반드시 재사용하세요.** 새 파일을 생성하지 마세요.",
        "JSON의 'agents[].name' 필드에 아래 이름을 그대로 입력하면 자동으로 로드됩니다.\n",
    ]
    for name, info in list(idx.items())[:max_agents]:
        lines.append(f"- `{name}`: {info['description']}")

    return "\n".join(lines)


def list_all() -> list[dict]:
    """UI용 전체 에이전트 목록."""
    return [
        {"name": name, "description": info["description"], "harness": info["harness"]}
        for name, info in get_index().items()
    ]


# ── git 동기화 ────────────────────────────────────────────────────────────────

async def sync_submodule() -> bool:
    """
    harness-100 서브모듈을 최신 상태로 업데이트.
    성공 시 인덱스 갱신 후 True 반환.
    """
    repo_dir = Path(__file__).parent
    if not (repo_dir / ".git").exists() and not (repo_dir / ".gitmodules").exists():
        logger.warning("[registry] .gitmodules 없음, 동기화 스킵")
        return False

    logger.info("[registry] harness-100 동기화 시작...")
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "submodule", "update", "--remote", "--merge", "harness-100",
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            refresh_index()
            logger.info("[registry] harness-100 동기화 완료 (%d개 에이전트)", len(_index))
            return True
        else:
            logger.error("[registry] 동기화 실패: %s", stderr.decode()[:200])
            return False
    except Exception as e:
        logger.error("[registry] 동기화 오류: %s", e)
        return False
