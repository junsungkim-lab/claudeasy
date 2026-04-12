"""
세션 히스토리 — run 완료 시 날짜별 MD 파일로 저장

저장 구조:
  claude-local/sessions/{project_name}/{YYYY-MM-DD}.md
  project_path 없는 보드 → sessions/_default/
"""
from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

SESSIONS_DIR = Path(__file__).parent / "sessions"
KST = timezone(timedelta(hours=9))
MAX_OUTPUT_CHARS = 500


def _project_name(project_path) -> str:
    if not project_path:
        return "_default"
    name = Path(project_path).name
    return re.sub(r"[^a-zA-Z0-9._-]", "_", name) or "_default"


def _today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _time_kst() -> str:
    return datetime.now(KST).strftime("%H:%M")


def _summarize(text: str) -> str:
    if not text:
        return "(출력 없음)"
    text = text.strip()
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + f"\n...(총 {len(text):,}자)"


def save_run_session(
    board: dict,
    run: dict,
    cards: list[dict],
    duration_seconds=None,
) -> Path:
    """
    run 완료 시 호출. 해당 날짜 MD 파일에 append.
    반환: 저장된 파일 경로
    """
    project_name = _project_name(board.get("project_path"))
    date_str = _today_kst()
    time_str = _time_kst()

    folder = SESSIONS_DIR / project_name
    folder.mkdir(parents=True, exist_ok=True)

    md_path = folder / f"{date_str}.md"

    # 에이전트 목록
    agent_names = list({c.get("agent_role", "?") for c in cards if c.get("agent_role")})
    agents_str = ", ".join(agent_names) if agent_names else "없음"

    # duration
    dur_str = ""
    if duration_seconds is not None:
        m, s = divmod(int(duration_seconds), 60)
        dur_str = f"{m}m {s}s" if m else f"{s}s"

    run_trigger = run.get("trigger", "manual")
    run_id = run.get("id", "?")
    board_name = board.get("name") or board.get("description") or "보드"
    project_label = board.get("project_path") or "없음"
    status = run.get("status", "?")

    lines = [
        f"\n---\n",
        f"## [{time_str}] {board_name} (Run #{run_id}, {run_trigger})\n",
        f"**Board**: {board_name} | **Project**: {project_label} | **Agents**: {agents_str}\n",
    ]

    for card in cards:
        title = card.get("title", "")
        agent = card.get("agent_role", "")
        output = card.get("output", "") or ""
        card_status = card.get("status", "")

        header = f"### {agent} — {title}" if agent else f"### {title}"
        lines.append(f"\n{header}\n")

        if card_status == "error":
            lines.append("> ❌ 오류 발생\n")
        elif card_status == "rejected":
            lines.append("> ✕ 거부됨\n")
        else:
            summary = _summarize(output)
            for ln in summary.splitlines():
                lines.append(f"> {ln}\n")

    footer_parts = [f"**Status**: {status}"]
    if dur_str:
        footer_parts.append(f"**Duration**: {dur_str}")
    lines.append(f"\n{' | '.join(footer_parts)}\n")

    with md_path.open("a", encoding="utf-8") as f:
        f.writelines(lines)

    return md_path


def get_all_projects() -> list[dict]:
    """sessions/ 아래 프로젝트 폴더 목록과 날짜 반환."""
    if not SESSIONS_DIR.exists():
        return []
    result = []
    for folder in sorted(SESSIONS_DIR.iterdir()):
        if not folder.is_dir():
            continue
        dates = sorted(
            [p.stem for p in folder.glob("*.md") if p.suffix == ".md"],
            reverse=True,
        )
        if dates:
            result.append({"project": folder.name, "dates": dates})
    return result


def get_session_content(project: str, date: str):
    """특정 프로젝트/날짜의 MD 내용 반환. 없으면 None."""
    path = SESSIONS_DIR / project / f"{date}.md"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")
