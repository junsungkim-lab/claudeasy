"""시스템 crontab 기반 보드 자동 실행 + harness-100 일일 동기화.

각 보드의 cron 잡은 OS crontab에 등록되므로 서버가 꺼져도 트리거가 살아있다.
서버가 재시작되면 /api/boards/{id}/schedule/trigger 엔드포인트로 파이프라인이 실행된다.
"""
from __future__ import annotations
import logging
import subprocess
import sys
import os
from datetime import datetime, timezone
from croniter import croniter

import db

logger = logging.getLogger(__name__)

# 이 프로젝트 루트 (run_board.py 위치)
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_RUNNER = os.path.join(_PROJECT_DIR, "run_board.py")
_PYTHON = sys.executable
_PORT = int(os.environ.get("PORT", 8100))

# crontab 마커: board별 블록을 식별하기 위한 prefix
_MARKER = "# claude-local"


def _read_crontab() -> str:
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    # 아직 crontab이 없으면 빈 문자열
    return result.stdout if result.returncode == 0 else ""


def _write_crontab(content: str):
    proc = subprocess.run(["crontab", "-"], input=content, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"crontab write failed: {proc.stderr}")


def _job_marker(board_id: int) -> str:
    return f"{_MARKER} board_{board_id}"


def _job_line(board_id: int, cron_expr: str) -> str:
    return f"{cron_expr} {_PYTHON} {_RUNNER} {board_id} {_PORT}"


def _remove_board_block(lines: list[str], board_id: int) -> list[str]:
    """crontab 라인 목록에서 해당 보드 블록(마커+잡라인) 제거."""
    marker = _job_marker(board_id)
    result, skip_next = [], False
    for line in lines:
        if skip_next:
            skip_next = False
            continue
        if line.strip() == marker or line.strip() == f"{marker} PAUSED":
            skip_next = True
            continue
        result.append(line)
    return result


# ── Public API ────────────────────────────────────────────────────────────────

def load_boards():
    """서버 시작 시 DB와 시스템 crontab 동기화."""
    # harness-100 일일 동기화는 별도 잡으로 등록
    _ensure_harness_sync_job()

    for board in db.get_boards():
        bid = board["id"]
        cron_expr = board.get("cron_expr")
        paused = board.get("cron_paused", False)
        if cron_expr and not paused:
            _upsert(bid, cron_expr)
        elif not cron_expr:
            _remove(bid)

    logger.info("[scheduler] crontab 동기화 완료")


def register_board(board_id: int, cron_expr: str):
    _upsert(board_id, cron_expr)
    logger.info("[scheduler] 등록: board_%d cron=%s", board_id, cron_expr)


def unregister_board(board_id: int):
    _remove(board_id)
    logger.info("[scheduler] 해제: board_%d", board_id)


def pause_board(board_id: int):
    """crontab 라인을 주석처리(PAUSED)."""
    raw = _read_crontab()
    lines = raw.splitlines()
    marker = _job_marker(board_id)
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == marker:
            # 마커를 PAUSED 마커로, 다음 잡 라인을 주석으로
            new_lines.append(f"{marker} PAUSED")
            i += 1
            if i < len(lines):
                new_lines.append(f"#{lines[i]}")
        else:
            new_lines.append(line)
        i += 1
    _write_crontab("\n".join(new_lines) + "\n")
    logger.info("[scheduler] 일시정지: board_%d", board_id)


def resume_board(board_id: int):
    """PAUSED 상태를 해제하고 crontab 라인 복원."""
    raw = _read_crontab()
    lines = raw.splitlines()
    marker_paused = f"{_job_marker(board_id)} PAUSED"
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == marker_paused:
            new_lines.append(_job_marker(board_id))
            i += 1
            if i < len(lines):
                # 앞의 # 제거
                new_lines.append(lines[i].lstrip("#"))
        else:
            new_lines.append(line)
        i += 1
    _write_crontab("\n".join(new_lines) + "\n")
    logger.info("[scheduler] 재개: board_%d", board_id)


def is_paused(board_id: int) -> bool:
    raw = _read_crontab()
    return f"{_job_marker(board_id)} PAUSED" in raw


def get_next_run_time(board_id: int):
    """cron_expr로 다음 실행 시각 계산 (ISO 8601, KST)."""
    board = db.get_board(board_id)
    if not board or not board.get("cron_expr"):
        return None
    if is_paused(board_id):
        return None
    try:
        import zoneinfo
        kst = zoneinfo.ZoneInfo("Asia/Seoul")
    except ImportError:
        from datetime import timezone, timedelta
        kst = timezone(timedelta(hours=9))
    now = datetime.now(tz=kst)
    cron = croniter(board["cron_expr"], now)
    nxt = cron.get_next(datetime)
    # tzinfo 붙이기
    if nxt.tzinfo is None:
        nxt = nxt.replace(tzinfo=kst)
    return nxt.isoformat()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _upsert(board_id: int, cron_expr: str):
    raw = _read_crontab()
    lines = raw.splitlines()
    lines = _remove_board_block(lines, board_id)
    lines.append(_job_marker(board_id))
    lines.append(_job_line(board_id, cron_expr))
    # 빈 줄 중복 방지
    content = "\n".join(lines).strip() + "\n"
    _write_crontab(content)


def _remove(board_id: int):
    raw = _read_crontab()
    if _job_marker(board_id) not in raw:
        return
    lines = raw.splitlines()
    lines = _remove_board_block(lines, board_id)
    content = "\n".join(lines).strip() + "\n"
    _write_crontab(content)


def _ensure_harness_sync_job():
    """harness-100 일일 동기화 잡 등록 (매일 04:00 KST)."""
    raw = _read_crontab()
    marker = f"{_MARKER} harness100_sync"
    if marker in raw:
        return
    sync_script = os.path.join(_PROJECT_DIR, "sync_harness.py")
    lines = raw.splitlines()
    lines.append(marker)
    lines.append(f"0 4 * * * {_PYTHON} {sync_script}")
    _write_crontab("\n".join(lines).strip() + "\n")
    logger.info("[scheduler] harness-100 동기화 잡 등록 (매일 04:00 KST)")
