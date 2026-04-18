"""
claude-local — 비동기 백그라운드 실행
- POST /api/boards          → 즉시 보드 + run 생성 + 백그라운드 파이프라인
- POST /api/boards/{id}/runs → 기존 보드 재실행
- WS /ws/board/{id}         → 보드 레벨 이벤트
- WS /ws/run/{run_id}       → run 레벨 카드 상태 이벤트
- WS /ws/card/{id}          → 카드 출력 스트리밍
"""
import asyncio
import json
import os
from pathlib import Path
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import subprocess

load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

import db
import agents_registry
import scheduler as sched
import session_logger
import github_trending as gh_trending
import github_oauth
from harness import generate_harness, run_card, agents_exist_on_disk, _run_claude, update_project_memory, has_unanswered_questions, generate_auto_answers, parse_artifact

# ── 실시간 구독자 관리 ───────────────────────────────────────────────────────
_board_subs: dict[int, set] = {}        # board_id → set[WebSocket]
_run_subs:   dict[int, set] = {}        # run_id   → set[WebSocket]
_card_state: dict[int, dict] = {}       # card_id  → {buffer, subs, done}
_board_event_log: dict[int, list] = {}  # board_id → 최근 이벤트 버퍼 (늦게 연결 시 재생)

# ── 프로젝트 선택 게이트 ─────────────────────────────────────────────────────
_project_gates:     dict[int, asyncio.Event] = {}  # board_id → Event
_project_responses: dict[int, str] = {}            # board_id → project_path

# ── 승인 게이트 ──────────────────────────────────────────────────────────────
_approval_gates:     dict[int, asyncio.Event] = {}  # card_id → Event
_approval_responses: dict[int, dict] = {}           # card_id → {action, message}

# ── 자동 답변 오케스트레이터 ─────────────────────────────────────────────────
_auto_answer_counts: dict[int, int] = {}  # card_id → 자동 답변 횟수 (루프 방지)

# ── 산출물 프로세스 레지스트리 ────────────────────────────────────────────────
_artifact_procs: dict[int, asyncio.subprocess.Process] = {}  # card_id → Process


async def _board_emit(board_id: int, event: dict):
    # 이벤트 버퍼에 저장 (최대 300개, harness_chunk는 누적)
    log = _board_event_log.setdefault(board_id, [])
    if event.get("type") == "harness_chunk" and log and log[-1].get("type") == "harness_chunk":
        log[-1] = {**log[-1], "text": log[-1].get("text", "") + event.get("text", "")}
    else:
        log.append(event)
    if len(log) > 300:
        _board_event_log[board_id] = log[-300:]

    for ws in list(_board_subs.get(board_id, [])):
        try:
            await ws.send_json(event)
        except Exception:
            _board_subs.get(board_id, set()).discard(ws)


async def _run_emit(run_id: int, event: dict):
    for ws in list(_run_subs.get(run_id, [])):
        try:
            await ws.send_json(event)
        except Exception:
            _run_subs.get(run_id, set()).discard(ws)


async def _card_emit(card_id: int, event: dict):
    state = _card_state.setdefault(card_id, {"buffer": "", "subs": set(), "done": False})
    if event.get("type") == "chunk":
        state["buffer"] += event.get("text", "")
    elif event.get("type") in ("card_done", "card_error"):
        state["done"] = True
    for ws in list(state["subs"]):
        try:
            await ws.send_json(event)
        except Exception:
            state["subs"].discard(ws)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    _recover_stuck_states()        # 서버 재시작 시 중단된 상태 복구
    agents_registry.get_index()   # 서버 시작 시 에이전트 인덱스 미리 로드
    sched.load_boards()
    yield
    for proc in list(_artifact_procs.values()):
        try:
            proc.kill()
        except Exception:
            pass


def _recover_stuck_states():
    """서버 재시작 시 인메모리 게이트가 사라져 stuck된 board/run/card 상태를 복구."""
    import sqlite3 as _sqlite3
    with _sqlite3.connect(db.DB_PATH) as conn:
        # 중단된 board 복구
        conn.execute("""
            UPDATE boards SET status='error'
            WHERE status IN ('generating', 'awaiting_project', 'running')
        """)
        # 중단된 run 복구
        conn.execute("""
            UPDATE runs SET status='error', finished_at=datetime('now')
            WHERE status IN ('generating', 'running')
        """)
        # 중단된 card 복구 (in_progress → error)
        conn.execute("""
            UPDATE cards SET status='error', updated_at=datetime('now')
            WHERE status = 'in_progress'
        """)


app = FastAPI(title="claude-local", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
HTML_LEGACY = Path(__file__).parent / "index.html"

# React 빌드 정적 파일 서빙
if STATIC_DIR.exists():
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")


@app.get("/health")
async def health():
    import shutil
    import subprocess

    cli_path = shutil.which("claude")
    if not cli_path:
        return {"claude_cli": False, "claude_authed": False, "version": None}

    # 버전 확인
    version = None
    try:
        r = subprocess.run(
            ["claude", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            version = r.stdout.strip().split("\n")[0]
    except Exception:
        pass

    # 인증 확인 — ~/.claude/ 디렉토리 내 인증 흔적 탐지
    claude_dir = Path.home() / ".claude"
    authed = (
        (claude_dir / ".credentials.json").exists()          # 구버전
        or (claude_dir / "credentials.json").exists()
        or any((claude_dir / "sessions").glob("*.json"))     # 세션 파일
        or (claude_dir / "history.jsonl").stat().st_size > 0 # 사용 기록
        if claude_dir.exists() else False
    )

    return {
        "claude_cli": True,
        "claude_authed": authed,
        "version": version,
    }


# ── Agents (harness-100 라이브러리) ───────────────────────────────────────────

@app.get("/api/agents")
async def list_agents(q: str = ""):
    """harness-100 에이전트 목록. q 파라미터로 검색."""
    if q:
        results = agents_registry.search_agents(q, limit=20)
        return [{"name": r["name"], "description": r["description"], "harness": r["harness"]} for r in results]
    return agents_registry.list_all()


@app.post("/api/agents/sync")
async def sync_agents():
    """harness-100 수동 동기화 트리거."""
    success = await agents_registry.sync_submodule()
    idx = agents_registry.get_index()
    return {"ok": success, "count": len(idx)}


# ── GitHub OAuth ──────────────────────────────────────────────────────────────

@app.get("/api/github/status")
async def github_status():
    user = github_oauth.get_github_user()
    return {
        "configured": github_oauth.is_configured(),
        "connected": github_oauth.is_connected(),
        "user": user,
    }


@app.post("/api/github/auth/start")
async def github_auth_start():
    if not github_oauth.is_configured():
        return {"error": "GITHUB_CLIENT_ID가 설정되지 않았습니다."}
    try:
        return await github_oauth.start_device_flow()
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/github/auth/poll")
async def github_auth_poll(body: dict):
    device_code = body.get("device_code")
    interval = body.get("interval", 5)
    if not device_code:
        return {"error": "device_code 필요"}
    try:
        token = await github_oauth.poll_device_flow(device_code, interval)
        if token:
            user = github_oauth.get_github_user()
            return {"ok": True, "user": user}
        return {"ok": False, "pending": True}
    except Exception as e:
        return {"error": str(e)}


@app.delete("/api/github/auth")
async def github_auth_disconnect():
    github_oauth.disconnect()
    return {"ok": True}


@app.get("/api/github/repos")
async def github_repos():
    if not github_oauth.is_connected():
        return {"error": "GitHub 미연결"}
    try:
        return await github_oauth.list_repos()
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/boards/{board_id}/github/sync")
async def github_sync(board_id: int):
    board = db.get_board(board_id)
    if not board or not board.get("github_repo"):
        return {"error": "GitHub repo가 연결되지 않은 보드입니다."}
    try:
        owner, repo = board["github_repo"].split("/", 1)
        dest = github_oauth.workspace_for_board(board_id)
        sha = await github_oauth.clone_or_pull(owner, repo, board.get("github_ref") or "main", dest)
        db.save_board_workspace(board_id, str(dest), sha)
        return {"ok": True, "workspace": str(dest), "sha": sha}
    except Exception as e:
        return {"error": str(e)}


# ── Projects ─────────────────────────────────────────────────────────────────

@app.get("/api/projects")
async def list_projects():
    """
    ~/Documents/ 및 ~/Desktop/ 에서 Claude-aware 프로젝트 스캔.
    CLAUDE.md 또는 .git 이 있는 디렉토리를 반환.
    """
    home = Path.home()
    scan_roots = [home / "Documents", home / "Desktop", home]
    found = {}  # path → info

    for root in scan_roots:
        if not root.exists():
            continue
        try:
            for d in sorted(root.iterdir()):
                if not d.is_dir() or d.name.startswith('.'):
                    continue
                has_claude_md = (d / "CLAUDE.md").exists()
                has_git       = (d / ".git").exists()
                if has_claude_md or has_git:
                    path_str = str(d)
                    if path_str not in found:
                        found[path_str] = {
                            "path": path_str,
                            "name": d.name,
                            "has_claude_md": has_claude_md,
                            "has_git": has_git,
                        }
        except PermissionError:
            continue

    # CLAUDE.md 있는 것 우선 정렬
    projects = sorted(found.values(), key=lambda x: (not x["has_claude_md"], x["name"]))
    return projects


# ── Boards ───────────────────────────────────────────────────────────────────

@app.get("/api/boards")
async def list_boards():
    boards = db.get_boards()
    for b in boards:
        latest_run_id = db.get_latest_run_id(b["id"])
        b["latest_run_id"] = latest_run_id
        b["cards"] = db.get_cards_for_run(latest_run_id) if latest_run_id else []
        b["agents"] = db.get_agents(b["id"])
        b["runs"] = db.get_runs(b["id"], limit=10)
        # project_path는 db에서 이미 포함됨
    return boards


@app.get("/api/boards/scheduled")
async def list_scheduled_boards():
    boards = db.get_boards()
    result = []
    for b in [b for b in boards if b.get("cron_expr")]:
        result.append({
            "id": b["id"],
            "name": b["name"],
            "cron_expr": b["cron_expr"],
            "status": b.get("status"),
            "next_run_at": sched.get_next_run_time(b["id"]),
            "paused": sched.is_paused(b["id"]),
        })
    return result


@app.post("/api/boards")
async def create_board(body: dict):
    user_request        = body.get("request", "").strip()
    use_tavily          = body.get("use_tavily", False)
    approval_mode       = body.get("approval_mode", "auto")
    project_path        = body.get("project_path") or None
    source_type         = body.get("source_type", "local")
    github_repo         = body.get("github_repo") or None
    github_installation_id = body.get("github_installation_id") or None
    github_ref          = body.get("github_ref", "main")

    if not user_request:
        return {"error": "내용을 입력하세요"}

    board_id = db.create_board(
        name=user_request[:60],
        description=user_request,
        approval_mode=approval_mode,
        project_path=project_path,
        status="generating",
    )

    if source_type == "github" and github_repo and github_installation_id:
        db.update_board_github(board_id, github_repo, int(github_installation_id), github_ref)
        # 보드 생성 직후 clone — 백그라운드로
        async def _clone_and_run():
            board = db.get_board(board_id)
            run_id = db.create_run(board_id, trigger="manual")
            try:
                resolved = await _resolve_board_workspace(board)
                await _run_pipeline(board_id, run_id, user_request, use_tavily, str(resolved))
            except Exception as exc:
                db.update_run_status(run_id, "error")
                db.update_board_status(board_id, "error")
                logger.error("[create_board] github clone failed: %s", exc)
        asyncio.create_task(_clone_and_run())
    else:
        run_id = db.create_run(board_id, trigger="manual")
        asyncio.create_task(_run_pipeline(board_id, run_id, user_request, use_tavily, project_path))

    return {"board_id": board_id, **db.get_board(board_id)}


@app.post("/api/boards/{board_id}/runs")
async def rerun_board(board_id: int, body: dict = {}):
    """기존 보드를 새 run으로 재실행"""
    board = db.get_board(board_id)
    if not board:
        return {"error": "보드를 찾을 수 없습니다"}

    run_id = db.create_run(board_id, trigger="rerun")
    asyncio.create_task(_run_pipeline(
        board_id, run_id, board["description"], False, board.get("project_path")
    ))
    return {"board_id": board_id, "run_id": run_id}


@app.get("/api/boards/{board_id}/runs")
async def get_runs(board_id: int):
    runs = db.get_runs(board_id)
    for r in runs:
        r["cards"] = db.get_cards_for_run(r["id"])
    return runs


@app.delete("/api/boards/{board_id}/runs/{run_id}")
async def delete_run(board_id: int, run_id: int):
    db.delete_run(run_id)
    return {"ok": True}


@app.delete("/api/boards/{board_id}")
async def delete_board(board_id: int):
    sched.unregister_board(board_id)
    db.delete_board(board_id)
    return {"ok": True}


@app.patch("/api/boards/{board_id}")
async def patch_board(board_id: int, body: dict):
    if "approval_mode" in body:
        db.update_board_approval_mode(board_id, body["approval_mode"])
    return {"ok": True}


# ── Schedule ──────────────────────────────────────────────────────────────────

@app.get("/api/boards/{board_id}/schedule")
async def get_schedule(board_id: int):
    board = db.get_board(board_id)
    if not board:
        return {"error": "not found"}
    cron_expr = board.get("cron_expr")
    next_run_at = None
    paused = False
    if cron_expr:
        next_run_at = sched.get_next_run_time(board_id)
        paused = sched.is_paused(board_id)
    return {
        "cron_expr": cron_expr,
        "enabled": bool(cron_expr),
        "paused": paused,
        "next_run_at": next_run_at,
    }


@app.put("/api/boards/{board_id}/schedule")
async def update_schedule(board_id: int, body: dict):
    cron_expr = body.get("cron_expr", "").strip() or None
    db.update_board_cron(board_id, cron_expr)
    if cron_expr:
        sched.register_board(board_id, cron_expr)
    else:
        sched.unregister_board(board_id)
    return {"ok": True, "cron_expr": cron_expr}


@app.delete("/api/boards/{board_id}/schedule")
async def delete_schedule(board_id: int):
    db.update_board_cron(board_id, None)
    sched.unregister_board(board_id)
    return {"ok": True}


@app.post("/api/boards/{board_id}/schedule/pause")
async def pause_schedule(board_id: int):
    sched.pause_board(board_id)
    return {"ok": True}


@app.post("/api/boards/{board_id}/schedule/resume")
async def resume_schedule(board_id: int):
    sched.resume_board(board_id)
    return {"ok": True}


@app.post("/api/boards/{board_id}/schedule/trigger")
async def trigger_now(board_id: int):
    board = db.get_board(board_id)
    if not board:
        return {"error": "not found"}
    run_id = db.create_run(board_id, trigger="cron")

    async def _trigger():
        try:
            workspace = await _resolve_board_workspace(board)
            project_path = str(workspace) if workspace else None
        except Exception as exc:
            logger.error("[trigger_now] workspace resolve failed: %s", exc)
            project_path = board.get("project_path")
        await _run_pipeline(board_id, run_id, board["description"], False, project_path)

    asyncio.create_task(_trigger())
    return {"board_id": board_id, "run_id": run_id}


# ── Feedback ──────────────────────────────────────────────────────────────────

@app.get("/api/cards/{card_id}/feedback")
async def get_feedback(card_id: int):
    return db.get_feedback(card_id)


@app.post("/api/cards/{card_id}/feedback")
async def add_feedback(card_id: int, body: dict):
    ftype     = body.get("type", "comment")
    content   = body.get("content", "")
    parent_id = body.get("parent_id", None)  # 스레드 답글용

    if ftype == "rerun":
        # 수동 재실행 시 자동 답변 카운트 리셋
        _auto_answer_counts.pop(card_id, None)
        card = db.get_card(card_id)
        if card:
            # 재실행 전: 현재 output 스냅샷 먼저 저장 (타임라인 순서 유지)
            prev_output = card.get("output") or ""
            if prev_output.strip():
                db.add_feedback(card_id, "output_snapshot", prev_output)
            # 그다음 재실행 노트 저장
            db.add_feedback(card_id, ftype, content, parent_id=parent_id)
            db.clear_card_output(card_id)
            # _card_state 초기화
            if card_id in _card_state:
                _card_state[card_id] = {"buffer": "", "subs": _card_state[card_id]["subs"], "done": False}
            # WS로 상태 리셋 알림 (backlog)
            run_id   = card["run_id"]
            board_id = card["board_id"]
            await _card_emit(card_id, {"type": "card_reset"})
            await _run_emit(run_id, {"type": "card_update", "card_id": card_id, "status": "backlog"})
            await _board_emit(board_id, {"type": "card_update", "card_id": card_id, "status": "backlog", "run_id": run_id})
            asyncio.create_task(_rerun_card(card_id, card, user_note=content))
        return {"ok": True}
    else:
        db.add_feedback(card_id, ftype, content, parent_id=parent_id)

    return {"ok": True}


# ── 에이전트 코멘트 답변 ─────────────────────────────────────────────────────

_active_ask_ids: set[int] = set()

@app.post("/api/feedback/{feedback_id}/ask")
async def ask_agent(feedback_id: int):
    """특정 코멘트에 카드 에이전트가 답변 생성."""
    # 이미 처리 중이거나 답변이 존재하면 중복 방지
    if feedback_id in _active_ask_ids:
        return {"ok": True, "skipped": "already_processing"}

    with __import__("sqlite3").connect(db.DB_PATH) as conn:
        conn.row_factory = __import__("sqlite3").Row
        fb = conn.execute("SELECT * FROM feedback WHERE id=?", (feedback_id,)).fetchone()
        existing = conn.execute(
            "SELECT id FROM feedback WHERE parent_id=? AND type='agent_reply'", (feedback_id,)
        ).fetchone()
    if not fb:
        return {"error": "피드백을 찾을 수 없습니다"}
    if existing:
        return {"ok": True, "skipped": "already_answered"}

    fb = dict(fb)
    card = db.get_card(fb["card_id"])
    if not card:
        return {"error": "카드를 찾을 수 없습니다"}

    board     = db.get_board(card["board_id"])
    agent_name = card.get("agent_role", "assistant")

    _active_ask_ids.add(feedback_id)
    asyncio.create_task(_agent_reply(feedback_id, fb, card, board, agent_name))
    return {"ok": True}


async def _agent_reply(feedback_id: int, fb: dict, card: dict, board: dict, agent_name: str):
    """Claude로 코멘트에 대한 에이전트 답변 생성 후 저장."""
    card_id = card["id"]
    run_id  = card["run_id"]
    board_id = card["board_id"]

    # 대화 체인 재구성 (현재 코멘트까지의 전체 맥락)
    all_feedback = db.get_feedback(card_id)
    fb_map = {f["id"]: f for f in all_feedback}

    def get_chain(fid: int) -> list[dict]:
        """현재 feedback까지 거슬러 올라가 대화 체인 반환."""
        chain = []
        cur = fb_map.get(fid)
        while cur:
            chain.append(cur)
            cur = fb_map.get(cur.get("parent_id")) if cur.get("parent_id") else None
        return list(reversed(chain))

    chain = get_chain(feedback_id)
    conversation = ""
    for item in chain:
        author = "나 (사용자)" if (item["author"] == "user" or not item["author"]) else item["author"]
        conversation += f"\n**{author}:** {item['content']}\n"

    prompt = f"""당신은 '{agent_name}' 에이전트입니다.
아래 작업 결과물에 대해 사용자와 나눈 대화입니다. 마지막 질문에 명확하고 간결하게 답변하세요.

## 작업 제목
{card.get('title', '')}

## 작업 결과물 요약
{(card.get('output') or '')[:1500]}

## 대화 내역
{conversation}
마지막 질문에 답변하세요."""

    system = f"You are {agent_name}, an AI agent. Reply in the same language as the user's comment. Be helpful and concise."

    chunks = []
    def on_chunk(c):
        chunks.append(c)

    try:
        await _run_claude(prompt=prompt, system_prompt=system, on_chunk=on_chunk)  # 3-tuple, ignore session
        reply_text = "".join(chunks)
        if reply_text.strip():
            db.add_feedback(card_id, "agent_reply", reply_text, author=agent_name, parent_id=feedback_id)
        else:
            db.add_feedback(card_id, "agent_reply", "(답변 없음)", author=agent_name, parent_id=feedback_id)
        # WS로 피드백 갱신 알림 (card / run / board 전체)
        await _card_emit(card_id, {"type": "feedback_update", "feedback_id": feedback_id})
        await _run_emit(run_id, {"type": "feedback_update", "card_id": card_id})
        await _board_emit(board_id, {"type": "feedback_update", "card_id": card_id, "run_id": run_id})
    except Exception as e:
        db.add_feedback(card_id, "agent_reply", f"[오류] {e}", author=agent_name, parent_id=feedback_id)
        await _card_emit(card_id, {"type": "feedback_update", "feedback_id": feedback_id})
    finally:
        _active_ask_ids.discard(feedback_id)


# ── 인스타 슬라이드 ───────────────────────────────────────────────────────────

_INSTA_OUTPUT = Path(__file__).parent / "output" / "insta"


@app.get("/api/cards/{card_id}/slides")
async def get_slides(card_id: int):
    """카드에 생성된 슬라이드 PNG 목록 반환."""
    slide_dir = _INSTA_OUTPUT / str(card_id)
    if not slide_dir.exists():
        return []
    files = sorted(slide_dir.glob("slide_*.png"))
    return [{"filename": f.name, "url": f"/api/cards/{card_id}/slides/{f.name}"} for f in files]


@app.get("/api/cards/{card_id}/slides/{filename}")
async def get_slide_file(card_id: int, filename: str):
    """개별 슬라이드 PNG 파일 서빙."""
    from fastapi import HTTPException
    path = _INSTA_OUTPUT / str(card_id) / filename
    if not path.exists() or not path.suffix == ".png":
        raise HTTPException(status_code=404, detail="슬라이드 파일 없음")
    return FileResponse(path, media_type="image/png")


# ── 산출물 실행 / 중지 ──────────────────────────────────────────────────────────

@app.post("/api/cards/{card_id}/run")
async def run_artifact(card_id: int):
    card = db.get_card(card_id)
    if not card or not card.get("run_command"):
        return {"error": "실행 가능한 산출물이 없습니다"}

    # 이미 실행 중이면 중지 후 재실행
    proc = _artifact_procs.get(card_id)
    if proc and proc.returncode is None:
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=3)
        except Exception:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass

    cwd = card.get("artifact_cwd") or str(Path.home())
    cmd = card["run_command"]
    new_proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    _artifact_procs[card_id] = new_proc
    port = card.get("artifact_port")
    await _card_emit(card_id, {"type": "artifact_started", "pid": new_proc.pid, "port": port})
    return {"pid": new_proc.pid, "port": port}


@app.post("/api/cards/{card_id}/stop")
async def stop_artifact(card_id: int):
    proc = _artifact_procs.get(card_id)
    if not proc or proc.returncode is not None:
        return {"error": "실행 중인 프로세스가 없습니다"}
    try:
        proc.terminate()
        await asyncio.wait_for(proc.wait(), timeout=5)
    except Exception:
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
    _artifact_procs.pop(card_id, None)
    await _card_emit(card_id, {"type": "artifact_stopped"})
    return {"ok": True}


@app.get("/api/cards/{card_id}/run-status")
async def get_run_status(card_id: int):
    proc = _artifact_procs.get(card_id)
    running = proc is not None and proc.returncode is None
    card = db.get_card(card_id)
    return {
        "running": running,
        "pid": proc.pid if running else None,
        "port": card.get("artifact_port") if card else None,
        "artifact_type": card.get("artifact_type") if card else None,
    }


# ── Approval ──────────────────────────────────────────────────────────────────

@app.post("/api/cards/{card_id}/approve")
async def approve_card(card_id: int, body: dict):
    action  = body.get("action", "approve")   # approve | reject | approve_with_note
    message = body.get("message", "")

    _approval_responses[card_id] = {"action": action, "message": message}
    gate = _approval_gates.get(card_id)
    if gate:
        gate.set()
    return {"ok": True}


# ── WS: 보드 이벤트 ───────────────────────────────────────────────────────────

@app.websocket("/ws/board/{board_id}")
async def ws_board(ws: WebSocket, board_id: int):
    await ws.accept()
    _board_subs.setdefault(board_id, set()).add(ws)
    try:
        board = db.get_board(board_id)
        if board:
            latest_run_id = db.get_latest_run_id(board_id)
            # 현재 보드 상태 전송
            await ws.send_json({
                "type": "board_state",
                "board_id": board_id,
                "status": board.get("status", ""),
                "approval_mode": board.get("approval_mode", "auto"),
                "cron_expr": board.get("cron_expr"),
                "project_path": board.get("project_path"),
                "agents": db.get_agents(board_id),
                "latest_run_id": latest_run_id,
                "cards": db.get_cards_for_run(latest_run_id) if latest_run_id else [],
                "runs": db.get_runs(board_id, limit=10),
            })
            # 놓친 이벤트 재생 (늦게 연결한 경우)
            for ev in _board_event_log.get(board_id, []):
                try:
                    await ws.send_json(ev)
                except Exception:
                    break
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _board_subs.get(board_id, set()).discard(ws)


# ── WS: run 이벤트 ────────────────────────────────────────────────────────────

@app.websocket("/ws/run/{run_id}")
async def ws_run(ws: WebSocket, run_id: int):
    await ws.accept()
    _run_subs.setdefault(run_id, set()).add(ws)
    try:
        run = db.get_run(run_id)
        if run:
            await ws.send_json({
                "type": "run_state",
                "run_id": run_id,
                "status": run["status"],
                "cards": db.get_cards_for_run(run_id),
            })
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _run_subs.get(run_id, set()).discard(ws)


# ── WS: 카드 출력 스트리밍 ────────────────────────────────────────────────────

@app.websocket("/ws/card/{card_id}")
async def ws_card(ws: WebSocket, card_id: int):
    await ws.accept()
    state = _card_state.setdefault(card_id, {"buffer": "", "subs": set(), "done": False})
    if state["buffer"]:
        await ws.send_json({"type": "buffer", "text": state["buffer"]})
    if state["done"]:
        await ws.send_json({"type": "card_done"})
        await ws.close()
        return
    state["subs"].add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        state["subs"].discard(ws)


# ── GitHub 워크스페이스 해결 ──────────────────────────────────────────────────

_workspace_locks: dict[int, asyncio.Lock] = {}


async def _resolve_board_workspace(board: dict):
    """github_repo가 있으면 clone/pull 후 워크스페이스 경로 반환.
    없으면 project_path 그대로 반환 (None 포함).
    """
    if not board.get("github_repo"):
        path = board.get("project_path") or board.get("workspace_path")
        return Path(path) if path else None

    board_id = board["id"]
    if board_id not in _workspace_locks:
        _workspace_locks[board_id] = asyncio.Lock()

    async with _workspace_locks[board_id]:
        owner, repo = board["github_repo"].split("/", 1)
        ref = board.get("github_ref") or "main"
        dest = github_oauth.workspace_for_board(board_id)

        sha = await github_oauth.clone_or_pull(owner, repo, ref, dest)
        db.save_board_workspace(board_id, str(dest), sha)
        logger.info("[workspace] board_%d → %s (sha=%s)", board_id, dest, sha[:7] if sha else "?")
        return dest


# ── 백그라운드 파이프라인 ─────────────────────────────────────────────────────

async def _run_pipeline(board_id: int, run_id: int, user_request: str,
                        use_tavily: bool, project_path: str = None):
    """harness 생성 → 카드 생성 → 순서대로 실행

    재사용 흐름:
      1) board에 이미 agents가 DB에 있고 .md 파일도 존재 → harness 스킵, 이전 run 카드로 tasks 구성
      2) 처음 실행 → harness 생성 → agents + tasks DB 저장
    """
    try:
        proj_label = f" [{Path(project_path).name}]" if project_path else ""

        # ── 재사용 여부 판단 ─────────────────────────────────────────────────
        existing_agents = db.get_agents(board_id)
        existing_agent_names = [a["name"] for a in existing_agents]
        can_reuse = bool(existing_agents) and agents_exist_on_disk(existing_agent_names, project_path)

        await _board_emit(board_id, {"type": "status", "text": f"🏗️  에이전트 팀 구성 중{proj_label}..."})
        await _run_emit(run_id,    {"type": "status", "text": f"🏗️  에이전트 팀 구성 중{proj_label}..."})

        parsed = await generate_harness(
            user_request=user_request,
            on_event=lambda e: asyncio.get_event_loop().call_soon(
                lambda ev=e: asyncio.ensure_future(_board_emit(board_id, ev))
            ),
            use_tavily=use_tavily,
            project_path=project_path,
            existing_agent_names=existing_agent_names if can_reuse else None,
        )

        reused        = parsed.get("reused", False)
        schedule      = parsed.get("schedule")
        needs_project = parsed.get("needs_project", False)

        # ── 프로젝트 필요 여부 확인 ──────────────────────────────────────────
        if needs_project and not project_path:
            db.update_board_status(board_id, "awaiting_project")
            gate = asyncio.Event()
            _project_gates[board_id] = gate

            await _board_emit(board_id, {
                "type": "awaiting_project",
                "board_id": board_id,
                "run_id": run_id,
                "agents": parsed.get("agents") or [],
                "tasks": parsed.get("tasks") or [],
            })
            await _run_emit(run_id, {"type": "awaiting_project"})

            await gate.wait()
            project_path = _project_responses.pop(board_id, None)
            _project_gates.pop(board_id, None)

            if not project_path:
                db.update_run_status(run_id, "error")
                db.update_board_status(board_id, "error")
                return

            # project_path DB에 저장
            db.update_board_project_path(board_id, project_path)
            db.update_board_status(board_id, "generating")

            # harness 재실행 (이번엔 project_path 있음)
            await _board_emit(board_id, {"type": "status", "text": f"🏗️  [{Path(project_path).name}] 에이전트 팀 구성 중..."})
            parsed = await generate_harness(
                user_request=user_request,
                on_event=lambda e: asyncio.get_event_loop().call_soon(
                    lambda ev=e: asyncio.ensure_future(_board_emit(board_id, ev))
                ),
                use_tavily=use_tavily,
                project_path=project_path,
                existing_agent_names=None,
            )
            reused   = False
            schedule = parsed.get("schedule")

        # ── agents 결정 ──────────────────────────────────────────────────────
        if reused:
            # 기존 DB 에이전트 그대로 사용
            agents = existing_agents  # list of dicts with name/role/color etc.
        else:
            agents = parsed.get("agents") or [{"name": "assistant", "role": "AI 어시스턴트"}]
            # 처음이면 DB에 저장
            if not existing_agents:
                for idx, ag in enumerate(agents):
                    db.create_agent(board_id, ag["name"], ag.get("role", ""), idx)

        # ── tasks 결정 ───────────────────────────────────────────────────────
        if reused:
            # 가장 최근 이전 run의 카드들로 tasks 재구성 (rejected 제외)
            prev_runs = db.get_runs(board_id, limit=20)
            prev_run = next((r for r in prev_runs if r["id"] != run_id), None)
            if prev_run:
                prev_cards = db.get_cards_for_run(prev_run["id"])
                tasks = [
                    {"title": c["title"], "description": c["description"], "agent": c["agent_role"],
                     "design_system": c.get("design_system")}
                    for c in prev_cards if c["status"] != "rejected"
                ]
            else:
                tasks = [{"title": user_request[:60], "description": user_request,
                          "agent": existing_agent_names[0] if existing_agent_names else "assistant"}]
        else:
            tasks = parsed.get("tasks") or [{"title": user_request[:60], "description": user_request,
                                              "agent": agents[0]["name"] if agents else "assistant"}]

        # ── cards 생성 (run 레벨) ────────────────────────────────────────────
        card_ids = []
        for t in tasks:
            cid = db.create_card(board_id, run_id, t.get("title", ""), t.get("description", ""),
                                 t.get("agent", ""), t.get("design_system"))
            card_ids.append(cid)

        db.update_run_status(run_id, "ready")
        db.update_board_status(board_id, "ready")

        if schedule:
            db.update_board_cron(board_id, schedule)
            sched.register_board(board_id, schedule)

        await _board_emit(board_id, {
            "type": "board_ready",
            "agents": db.get_agents(board_id),
            "run_id": run_id,
            "cards": db.get_cards_for_run(run_id),
            "schedule": schedule,
            "reused": reused,
        })
        await _run_emit(run_id, {
            "type": "run_ready",
            "cards": db.get_cards_for_run(run_id),
        })

        # ── 카드 병렬 실행 ─────────────────────────────────────────────────
        board = db.get_board(board_id)
        approval_mode = board.get("approval_mode", "auto")

        async def _run_single_card(card_id: int, task: dict):
            agent_name = task.get("agent", agents[0]["name"])

            # ── 승인 게이트 ──────────────────────────────────────────────
            if approval_mode == "manual":
                db.update_card_status(card_id, "awaiting_approval")
                gate = asyncio.Event()
                _approval_gates[card_id] = gate

                await _board_emit(board_id, {
                    "type": "approval_needed",
                    "card_id": card_id,
                    "card_title": task.get("title", ""),
                    "card_description": task.get("description", ""),
                    "agent": agent_name,
                    "run_id": run_id,
                })
                await _run_emit(run_id, {
                    "type": "card_update",
                    "card_id": card_id,
                    "status": "awaiting_approval",
                    "agent": agent_name,
                })

                await gate.wait()
                response = _approval_responses.pop(card_id, {})
                _approval_gates.pop(card_id, None)

                if response.get("action") == "reject":
                    db.update_card_status(card_id, "rejected")
                    await _run_emit(run_id, {
                        "type": "card_update",
                        "card_id": card_id,
                        "status": "rejected",
                    })
                    return

                if response.get("action") == "approve_with_note" and response.get("message"):
                    task = dict(task)
                    task["description"] = task.get("description", "") + f"\n\n[사용자 메모] {response['message']}"

            # ── 카드 실행 ────────────────────────────────────────────────
            db.update_card_status(card_id, "in_progress")
            db.set_agent_status(board_id, agent_name, "working")
            await _run_emit(run_id, {
                "type": "card_update",
                "card_id": card_id,
                "status": "in_progress",
                "agent": agent_name,
            })
            await _board_emit(board_id, {
                "type": "card_update",
                "card_id": card_id,
                "status": "in_progress",
                "agent": agent_name,
                "run_id": run_id,
            })

            def on_chunk(chunk, cid=card_id):
                db.append_card_output(cid, chunk)
                asyncio.ensure_future(_card_emit(cid, {"type": "chunk", "text": chunk}))

            def on_new_session(sid, cid=card_id):
                db.save_card_session_id(cid, sid)

            try:
                await run_card(
                    card_title=task.get("title", ""),
                    card_description=task.get("description", ""),
                    agent_name=agent_name,
                    context=user_request,
                    on_chunk=on_chunk,
                    session_id=db.get_card_session_id(card_id),
                    on_session_id=on_new_session,
                    project_path=project_path,
                    design_system=task.get("design_system"),
                )
                db.update_card_status(card_id, "done")
                db.set_agent_status(board_id, agent_name, "idle")
                # artifact 파싱 → DB 저장
                _final_card = db.get_card(card_id)
                _artifact = parse_artifact(_final_card.get("output") or "")
                if _artifact:
                    db.update_card_artifact(
                        card_id,
                        _artifact["type"],
                        _artifact["run_command"],
                        _artifact.get("port"),
                        _artifact.get("cwd"),
                    )
                await _card_emit(card_id, {"type": "card_done", "artifact": _artifact})
                await _run_emit(run_id, {
                    "type": "card_update",
                    "card_id": card_id,
                    "status": "done",
                    "artifact": _artifact,
                })
                await _board_emit(board_id, {
                    "type": "card_update",
                    "card_id": card_id,
                    "status": "done",
                    "run_id": run_id,
                    "artifact": _artifact,
                })
                # 프로젝트 장기 기억 업데이트 (백그라운드)
                if project_path:
                    final_card = db.get_card(card_id)
                    asyncio.create_task(update_project_memory(
                        project_path, task.get("title", ""), final_card.get("output") or ""
                    ))
                # 인스타 캐러셀 후처리 (insta_creator 에이전트일 때)
                if "insta" in agent_name.lower():
                    final_card = db.get_card(card_id)
                    async def _do_carousel(cid=card_id, out=final_card.get("output") or ""):
                        from core.insta.generator import generate_carousel
                        paths = await generate_carousel(cid, out)
                        if paths:
                            await _card_emit(cid, {"type": "slides_ready", "count": len(paths)})
                    asyncio.create_task(_do_carousel())
                # 자동 답변 오케스트레이터 (질문 감지 → 자동 재실행)
                else:
                    final_card = db.get_card(card_id)
                    asyncio.create_task(_try_auto_answer(
                        card_id, final_card, final_card.get("output") or "", board, task
                    ))

            except Exception as e:
                error_text = f"\n\n---\n\n**[오류 발생]**\n```\n{e}\n```"
                db.append_card_output(card_id, error_text)
                db.update_card_status(card_id, "error")
                db.set_agent_status(board_id, agent_name, "idle")
                await _card_emit(card_id, {"type": "card_error", "text": str(e)})
                await _run_emit(run_id, {
                    "type": "card_update",
                    "card_id": card_id,
                    "status": "error",
                })
                await _board_emit(board_id, {
                    "type": "card_update",
                    "card_id": card_id,
                    "status": "error",
                    "run_id": run_id,
                })

        await asyncio.gather(*[_run_single_card(cid, t) for cid, t in zip(card_ids, tasks)])

        db.update_run_status(run_id, "done")
        db.update_board_status(board_id, "done")
        await _run_emit(run_id, {"type": "run_done"})
        await _board_emit(board_id, {"type": "board_done", "run_id": run_id})

        # ── GitHub 자동 push ──────────────────────────────────────────────────
        if project_path and github_oauth.is_connected():
            asyncio.create_task(_github_push(board_id, board_name=user_request[:60], project_path=project_path))

        # ── 세션 히스토리 저장 ───────────────────────────────────────────────
        try:
            board_snap = db.get_board(board_id)
            run_snap   = db.get_run(run_id)
            cards_snap = db.get_cards_for_run(run_id)
            if board_snap and run_snap:
                session_logger.save_run_session(board_snap, run_snap, cards_snap)
        except Exception:
            pass  # 저장 실패해도 파이프라인에 영향 없음

    except Exception as e:
        db.update_run_status(run_id, "error")
        db.update_board_status(board_id, "error")
        await _run_emit(run_id, {"type": "error", "text": str(e)})
        await _board_emit(board_id, {"type": "error", "text": str(e)})


async def _github_push(board_id: int, board_name: str, project_path: str):
    """파이프라인 완료 후 GitHub repo 생성 or 업데이트."""
    try:
        board = db.get_board(board_id)
        dest = Path(project_path)

        if not board.get("github_repo"):
            # 신규 repo 생성
            slug = github_oauth.repo_slug(board_name)
            await _board_emit(board_id, {"type": "status", "text": f"📦 GitHub repo 생성 중: {slug}"})
            repo_info = await github_oauth.create_repo(slug, description=board_name)
            full_name = repo_info["full_name"]
            db.update_board_github(board_id, full_name, None, "main")
            await github_oauth.init_and_push(dest, repo_info, message=f"feat: {board_name}")
            await _board_emit(board_id, {
                "type": "github_pushed",
                "repo": full_name,
                "url": repo_info["html_url"],
            })
            logger.info("[github] 신규 repo push: %s", full_name)
        else:
            # 기존 repo에 변경사항 push
            await github_oauth.commit_and_push(dest, message=f"update: {board_name}")
            await _board_emit(board_id, {
                "type": "github_pushed",
                "repo": board["github_repo"],
                "url": f"https://github.com/{board['github_repo']}",
            })
            logger.info("[github] 기존 repo push: %s", board["github_repo"])
    except Exception as e:
        logger.error("[github] push 실패: %s", e)
        await _board_emit(board_id, {"type": "github_push_error", "text": str(e)})


async def _rerun_card(card_id: int, card: dict, user_note: str = ""):
    """개별 카드 재실행. user_note가 있으면 프롬프트에 추가 요구사항으로 포함."""
    board_id     = card["board_id"]
    run_id       = card["run_id"]
    agent_name   = card.get("agent_role", "assistant")
    board        = db.get_board(board_id)
    session_id   = db.get_card_session_id(card_id)
    project_path = board.get("project_path") if board else None

    db.update_card_status(card_id, "in_progress")
    db.set_agent_status(board_id, agent_name, "working")
    await _run_emit(run_id, {"type": "card_update", "card_id": card_id, "status": "in_progress", "agent": agent_name})
    await _board_emit(board_id, {"type": "card_update", "card_id": card_id, "status": "in_progress", "agent": agent_name, "run_id": run_id})

    def on_chunk(chunk):
        db.append_card_output(card_id, chunk)
        asyncio.ensure_future(_card_emit(card_id, {"type": "chunk", "text": chunk}))

    def on_new_session(sid, cid=card_id):
        db.save_card_session_id(cid, sid)

    base_description = card.get("description", "")
    card_description = (
        f"{base_description}\n\n[사용자 추가 요구사항]\n{user_note.strip()}"
        if user_note and user_note.strip()
        else base_description
    )

    try:
        await run_card(
            card_title=card.get("title", ""),
            card_description=card_description,
            agent_name=agent_name,
            context=board.get("description", "") if board else "",
            on_chunk=on_chunk,
            session_id=session_id,
            on_session_id=on_new_session,
            project_path=project_path,
            design_system=card.get("design_system"),
        )
        db.update_card_status(card_id, "done")
        db.set_agent_status(board_id, agent_name, "idle")
        # artifact 파싱 → DB 저장
        _rerun_card_data = db.get_card(card_id)
        _rerun_artifact = parse_artifact(_rerun_card_data.get("output") or "")
        if _rerun_artifact:
            db.update_card_artifact(
                card_id,
                _rerun_artifact["type"],
                _rerun_artifact["run_command"],
                _rerun_artifact.get("port"),
                _rerun_artifact.get("cwd"),
            )
        await _card_emit(card_id, {"type": "card_done", "artifact": _rerun_artifact})
        await _run_emit(run_id, {"type": "card_update", "card_id": card_id, "status": "done", "artifact": _rerun_artifact})
        await _board_emit(board_id, {"type": "card_update", "card_id": card_id, "status": "done", "run_id": run_id, "artifact": _rerun_artifact})
        # 프로젝트 장기 기억 업데이트 (백그라운드)
        if project_path:
            final_card = db.get_card(card_id)
            asyncio.create_task(update_project_memory(
                project_path, card.get("title", ""), final_card.get("output") or ""
            ))
        # 인스타 캐러셀 후처리 (insta_creator 에이전트일 때)
        if "insta" in agent_name.lower():
            final_card = db.get_card(card_id)
            async def _do_carousel_rerun(cid=card_id, out=final_card.get("output") or ""):
                from core.insta.generator import generate_carousel
                paths = await generate_carousel(cid, out)
                if paths:
                    await _card_emit(cid, {"type": "slides_ready", "count": len(paths)})
            asyncio.create_task(_do_carousel_rerun())
        # 자동 답변 오케스트레이터 (질문 감지 → 자동 재실행)
        else:
            final_card = db.get_card(card_id)
            asyncio.create_task(_try_auto_answer(
                card_id, final_card, final_card.get("output") or "", board,
                {"title": card.get("title", "")}
            ))
    except Exception as e:
        error_text = f"\n\n---\n\n**[오류 발생]**\n```\n{e}\n```"
        db.append_card_output(card_id, error_text)
        db.update_card_status(card_id, "error")
        db.set_agent_status(board_id, agent_name, "idle")
        await _card_emit(card_id, {"type": "card_error", "text": str(e)})
        await _run_emit(run_id, {"type": "card_update", "card_id": card_id, "status": "error"})
        await _board_emit(board_id, {"type": "card_update", "card_id": card_id, "status": "error", "run_id": run_id})


async def _try_auto_answer(
    card_id: int, card: dict, output: str, board: dict, task: dict
):
    """
    카드 output에 질문이 감지되면 오케스트레이터가 자동 답변 생성 후 재실행.
    카드당 최대 1회 (수동 재실행 시 카운트 리셋).
    """
    # 루프 방지: 이미 자동 답변한 적 있으면 중단
    if _auto_answer_counts.get(card_id, 0) >= 1:
        return
    if not has_unanswered_questions(output):
        return

    _auto_answer_counts[card_id] = _auto_answer_counts.get(card_id, 0) + 1

    board_id = card["board_id"]
    run_id   = card["run_id"]

    # WS로 자동 답변 생성 중 알림
    await _card_emit(card_id, {"type": "auto_answering"})
    await _board_emit(board_id, {"type": "card_update", "card_id": card_id,
                                  "status": "auto_answering", "run_id": run_id})

    try:
        answers = await generate_auto_answers(
            agent_output=output,
            card_title=task.get("title", card.get("title", "")),
            board_context=board.get("description", ""),
            project_path=board.get("project_path"),
        )
        if not answers:
            return

        # 스냅샷 저장 후 자동 재실행
        if output.strip():
            db.add_feedback(card_id, "output_snapshot", output)
        db.add_feedback(card_id, "rerun", f"[자동 답변]\n{answers}", author="auto")
        db.clear_card_output(card_id)
        if card_id in _card_state:
            _card_state[card_id] = {"buffer": "", "subs": _card_state[card_id]["subs"], "done": False}

        await _card_emit(card_id, {"type": "card_reset"})
        await _run_emit(run_id, {"type": "card_update", "card_id": card_id, "status": "backlog"})
        await _board_emit(board_id, {"type": "card_update", "card_id": card_id,
                                      "status": "backlog", "run_id": run_id})

        fresh_card = db.get_card(card_id)
        await _rerun_card(card_id, fresh_card, user_note=answers)

    except Exception as e:
        await _card_emit(card_id, {"type": "auto_answer_error", "text": str(e)})


# ── Project Gate ─────────────────────────────────────────────────────────────

@app.post("/api/boards/{board_id}/set-project")
async def set_project(board_id: int, body: dict):
    """awaiting_project 상태의 보드에 프로젝트 경로를 지정하고 파이프라인 재개."""
    project_path = body.get("project_path", "").strip()
    if not project_path:
        return {"error": "project_path 필수"}

    _project_responses[board_id] = project_path
    gate = _project_gates.get(board_id)
    if gate:
        gate.set()
    return {"ok": True, "project_path": project_path}


@app.post("/api/projects/create")
async def create_project(body: dict):
    """새 프로젝트 폴더 생성 후 경로 반환."""
    name = body.get("name", "").strip()
    if not name:
        return {"error": "name 필수"}

    import re as _re
    safe = _re.sub(r"[^a-zA-Z0-9가-힣._-]", "-", name).strip("-")
    if not safe:
        return {"error": "유효하지 않은 이름"}

    base = Path.home() / "Documents"
    project_path = base / safe

    if project_path.exists():
        return {"path": str(project_path), "existed": True}

    project_path.mkdir(parents=True, exist_ok=True)
    return {"path": str(project_path), "existed": False}


# ── Sessions (히스토리) ───────────────────────────────────────────────────────

@app.get("/api/sessions")
async def list_sessions():
    """프로젝트별 날짜 목록 반환."""
    return session_logger.get_all_projects()


@app.get("/api/sessions/{project}/{date}")
async def get_session(project: str, date: str):
    """특정 날짜 MD 내용 반환."""
    content = session_logger.get_session_content(project, date)
    if content is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="세션 파일을 찾을 수 없습니다")
    return {"project": project, "date": date, "content": content}


# ── GitHub Trending ───────────────────────────────────────────────────────────

@app.get("/api/trending")
async def list_trending(language: str = "", since: str = "weekly", limit: int = 20):
    """GitHub 트렌딩 레포 목록."""
    try:
        repos = await gh_trending.search_trending(language=language, since=since, limit=limit)
        return repos
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/trending/clones")
async def list_clones():
    """로컬에 클론된 레포 목록."""
    return gh_trending.list_clones()


_trending_ws_subs: dict[str, set] = {}  # "{owner}__{repo}" → set[WebSocket]


@app.post("/api/trending/analyze")
async def analyze_trending(body: dict):
    """레포 클론 + Claude 분석. analyze_id로 WS 스트리밍."""
    owner        = body.get("owner", "")
    repo         = body.get("repo", "")
    project_path = body.get("project_path") or None

    if not owner or not repo:
        return {"error": "owner, repo 필수"}

    analyze_id = f"{owner}__{repo}"
    asyncio.create_task(_do_analyze(analyze_id, owner, repo, project_path))
    return {"analyze_id": analyze_id}


async def _do_analyze(analyze_id: str, owner: str, repo: str, project_path):
    from harness import _run_claude, load_project_context

    async def emit(event: dict):
        for ws in list(_trending_ws_subs.get(analyze_id, [])):
            try:
                await ws.send_json(event)
            except Exception:
                _trending_ws_subs.get(analyze_id, set()).discard(ws)

    try:
        await emit({"type": "status", "text": f"⬇️ {owner}/{repo} 클론 중..."})
        repo_path = await gh_trending.async_clone_repo(owner, repo)

        await emit({"type": "status", "text": "📖 레포 분석 중..."})
        summary = gh_trending.read_repo_summary(repo_path)

        project_context = load_project_context(project_path) if project_path else ""

        system = (
            "You are a senior software architect. Analyze the given repository and explain:\n"
            "1. What it does and its key technical innovations\n"
            "2. How it could be applied to or integrated with the current project\n"
            "3. Concrete next steps to apply it (as actionable tasks)\n"
            "Respond in Korean. Be concise and practical."
        )

        prompt = f"## 레포: {owner}/{repo}\n\n{summary}"
        if project_context:
            prompt += f"\n\n{project_context}"

        chunks = []

        def on_chunk(c):
            chunks.append(c)
            asyncio.ensure_future(emit({"type": "chunk", "text": c}))

        output, _, _err = await _run_claude(prompt=prompt, system_prompt=system, on_chunk=on_chunk)
        await emit({"type": "done", "output": output, "repo_path": str(repo_path)})

    except Exception as e:
        await emit({"type": "error", "text": str(e)})


@app.websocket("/ws/trending/{analyze_id}")
async def ws_trending(ws: WebSocket, analyze_id: str):
    await ws.accept()
    _trending_ws_subs.setdefault(analyze_id, set()).add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _trending_ws_subs.get(analyze_id, set()).discard(ws)


@app.post("/api/trending/apply")
async def apply_trending(body: dict):
    """분석 결과를 보드로 변환."""
    analysis     = body.get("analysis", "")
    owner        = body.get("owner", "")
    repo         = body.get("repo", "")
    project_path = body.get("project_path") or None

    if not analysis:
        return {"error": "analysis 필수"}

    request = f"{owner}/{repo} 레포 적용:\n\n{analysis}"
    board_id = db.create_board(
        name=f"{owner}/{repo} 적용",
        description=request,
        approval_mode="manual",
        project_path=project_path,
        status="generating",
    )
    run_id = db.create_run(board_id, trigger="manual")
    asyncio.create_task(_run_pipeline(board_id, run_id, request, False, project_path))
    return {"board_id": board_id, "run_id": run_id}


@app.delete("/api/trending/clones/{owner}/{repo}")
async def delete_clone(owner: str, repo: str):
    ok = gh_trending.delete_clone(owner, repo)
    return {"ok": ok}


# ── SPA Fallback ─────────────────────────────────────────────────────────────

@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """React SPA: /api, /ws, /health 이외 모든 경로 → index.html"""
    spa_index = STATIC_DIR / "index.html"
    if spa_index.exists():
        return HTMLResponse(spa_index.read_text())
    # 개발 중 (빌드 전): 레거시 index.html 서빙
    if HTML_LEGACY.exists():
        return HTMLResponse(HTML_LEGACY.read_text())
    return HTMLResponse(
        "<h1>claude-local</h1><p>Run: <code>cd web && bun run build</code></p>",
        status_code=200,
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8100))
    print(f"\n✓ claude-local → http://localhost:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)
