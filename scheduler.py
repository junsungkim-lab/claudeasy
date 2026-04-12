"""APScheduler — 보드 자동 실행 (runs 기반) + harness-100 일일 동기화"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import db
import agents_registry
import session_logger
from harness import generate_harness, run_card

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="Asia/Seoul")


async def _execute_board(board_id: int):
    board = db.get_board(board_id)
    if not board:
        return
    logger.info("[scheduler] 보드 실행: %s", board["name"])

    run_id       = db.create_run(board_id, trigger="cron")
    project_path = board.get("project_path")

    def noop(e): pass

    existing_agents = db.get_agents(board_id)
    existing_names  = [a["name"] for a in existing_agents]

    parsed = await generate_harness(
        user_request=board["description"] or board["name"],
        on_event=noop,
        project_path=project_path,
        existing_agent_names=existing_names if existing_agents else None,
    )
    reused = parsed.get("reused", False)

    if reused:
        agents = existing_agents
        # 가장 최근 이전 run 카드에서 tasks 재구성
        prev_runs = db.get_runs(board_id, limit=20)
        prev_run  = next((r for r in prev_runs if r["id"] != run_id), None)
        if prev_run:
            prev_cards = db.get_cards_for_run(prev_run["id"])
            tasks = [
                {"title": c["title"], "description": c["description"], "agent": c["agent_role"]}
                for c in prev_cards if c["status"] != "rejected"
            ]
        else:
            tasks = []
    else:
        agents = parsed.get("agents", [{"name": "assistant", "role": ""}])
        tasks  = parsed.get("tasks", [])

    # agents: board 레벨 (없으면 생성, reused면 이미 있음)
    if not reused and not existing_agents:
        for idx, ag in enumerate(agents):
            db.create_agent(board_id, ag["name"], ag.get("role", ""), idx)

    context = board["description"] or board["name"]
    session_id = None

    db.update_run_status(run_id, "running")

    for t in tasks:
        agent_name = t.get("agent", agents[0]["name"])
        cid = db.create_card(board_id, run_id, t.get("title", ""), t.get("description", ""), agent_name)
        db.update_card_status(cid, "in_progress")
        chunks = []
        try:
            _, session_id = await run_card(
                card_title=t.get("title", ""),
                card_description=t.get("description", ""),
                agent_name=agent_name,
                context=context,
                on_chunk=lambda c: chunks.append(c),
                session_id=session_id,
                project_path=project_path,
            )
            db.append_card_output(cid, "".join(chunks))
            db.update_card_status(cid, "done")
            context += f"\n\n## {t.get('title','')} 결과\n{''.join(chunks)}"
        except Exception as e:
            db.update_card_status(cid, "error")
            logger.error("[scheduler] 카드 오류: %s", e)

    db.update_run_status(run_id, "done")
    db.update_board_status(board_id, "done")

    # 세션 히스토리 저장
    try:
        board_snap = db.get_board(board_id)
        run_snap   = db.get_run(run_id)
        cards_snap = db.get_cards_for_run(run_id)
        if board_snap and run_snap:
            session_logger.save_run_session(board_snap, run_snap, cards_snap)
    except Exception:
        pass


def load_boards():
    # harness-100 일일 동기화 (매일 오전 4시)
    scheduler.add_job(
        _sync_harness100,
        CronTrigger.from_crontab("0 4 * * *", timezone="Asia/Seoul"),
        id="harness100_sync",
        replace_existing=True,
    )
    logger.info("[scheduler] harness-100 일일 동기화 등록 (매일 04:00 KST)")

    for board in db.get_boards():
        if board.get("cron_expr"):
            _register(board["id"], board["cron_expr"])


async def _sync_harness100():
    """harness-100 서브모듈 최신화 + 인덱스 갱신"""
    success = await agents_registry.sync_submodule()
    if success:
        logger.info("[scheduler] harness-100 동기화 완료")


def _register(board_id: int, cron_expr: str):
    job_id = f"board_{board_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    scheduler.add_job(
        _execute_board,
        CronTrigger.from_crontab(cron_expr, timezone="Asia/Seoul"),
        id=job_id,
        args=[board_id],
        replace_existing=True,
    )
    logger.info("[scheduler] 등록: board_%d cron=%s", board_id, cron_expr)


def register_board(board_id: int, cron_expr: str):
    _register(board_id, cron_expr)


def unregister_board(board_id: int):
    job_id = f"board_{board_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)


def pause_board(board_id: int):
    job_id = f"board_{board_id}"
    job = scheduler.get_job(job_id)
    if job:
        job.pause()


def resume_board(board_id: int):
    job_id = f"board_{board_id}"
    job = scheduler.get_job(job_id)
    if job:
        job.resume()


def is_paused(board_id: int) -> bool:
    job_id = f"board_{board_id}"
    job = scheduler.get_job(job_id)
    if not job:
        return False
    return job.next_run_time is None


def get_next_run_time(board_id: int):
    job_id = f"board_{board_id}"
    job = scheduler.get_job(job_id)
    if not job or not job.next_run_time:
        return None
    # ISO 8601 문자열로 반환
    return job.next_run_time.isoformat()
