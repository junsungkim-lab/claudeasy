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
import logging
import os
import re
from pathlib import Path
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import subprocess

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

import db
import agents_registry
import scheduler as sched
import notifier
import session_logger
import github_trending as gh_trending
import github_oauth
from harness import generate_harness, run_card, agents_exist_on_disk, _run_claude, update_project_memory, has_unanswered_questions, generate_auto_answers, parse_artifact, _sanitize_sdk_usage

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
_artifact_watchers: dict[int, asyncio.Task] = {}  # card_id → early-exit watcher task


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


# ── Classification & Orchestration ───────────────────────────────────────────

async def _classify_request(title: str, project_path: str = None) -> dict:
    """orchestrator 1턴: 요청 분류"""
    from harness import HARNESS_CLASSIFY_SYSTEM

    output_chunks = []
    try:
        await _run_claude_for_classification(
            prompt=title,
            system_prompt=HARNESS_CLASSIFY_SYSTEM,
            on_chunk=lambda c: output_chunks.append(c),
            cwd=Path(project_path) if project_path else Path.home(),
            timeout=60,
        )
    except Exception as e:
        logger.error("[_classify_request] Claude call failed: %s", e)
        return {"kind": "build", "summary": title}

    text = "".join(output_chunks).strip()

    # JSON 추출 (마크다운 펜스 있을 수 있음)
    try:
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        logger.error("[_classify_request] JSON parse failed: %s", e)
        return {"kind": "build", "summary": title}


async def _provision_automation(board_id: int, automation: dict, project_path: str):
    """automation 보드 스크립트 개발 및 설정"""
    from harness import HARNESS_TOOL_DEV_SYSTEM

    tool_dir = Path.home() / ".claude-local-workspaces" / f"automation-{board_id}"
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "tools").mkdir(exist_ok=True)

    db.update_board_fields(board_id, {"automation_tool_dir": str(tool_dir)})

    # 도구 스크립트 개발 카드들 생성
    tool_agents = automation.get("tool_agents", [])
    for ta in tool_agents:
        card_id = db.insert_card(board_id, ta.get("task", ""), "in_progress", agent_role="python-dev")
        try:
            # 도구 개발을 위해 Claude 호출
            prompt = f"""Create a standalone Python script for:
{ta.get('task', '')}

The script should:
- Be executable as: python {ta.get('file', 'tool.py')}
- Use os.environ.get() for sensitive values
- Print progress to stdout
- Exit with 0 on success, non-zero on failure
- Have a requirements.txt list of dependencies
- Have a .env.example file listing all env vars needed

Create all three files in the provided directory."""

            output_chunks = []
            try:
                await _run_claude_for_classification(
                    prompt=prompt,
                    system_prompt=HARNESS_TOOL_DEV_SYSTEM,
                    on_chunk=lambda c: output_chunks.append(c),
                    cwd=tool_dir,
                )
                result = "".join(output_chunks)
                db.update_card(card_id, status="done", output=result[:2000])
            except Exception as e:
                db.update_card(card_id, status="error", output=f"Tool development failed: {str(e)[:300]}")
        except Exception as e:
            db.update_card(card_id, status="error", output=f"Tool card error: {str(e)[:300]}")

    # requirements.txt 있으면 의존성 설치
    req_file = tool_dir / "requirements.txt"
    if req_file.exists():
        card_id = db.insert_card(board_id, "의존성 설치 중...", "in_progress", agent_role="setup")
        try:
            proc = await asyncio.create_subprocess_exec(
                "bash", "-c",
                "python -m venv .venv && .venv/bin/pip install -r requirements.txt -q",
                cwd=str(tool_dir),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            if proc.returncode == 0:
                db.update_card(card_id, status="done", output="의존성 설치 완료")
            else:
                db.update_card(card_id, status="error", output=stderr.decode()[:500])
                return
        except Exception as e:
            db.update_card(card_id, status="error", output=str(e)[:300])
            return

    # .env.example 있으면 env_input 카드
    env_example = tool_dir / ".env.example"
    env_vars = automation.get("env_vars", [])
    if env_example.exists() or env_vars:
        if not env_vars and env_example.exists():
            # .env.example에서 파싱
            try:
                example_text = env_example.read_text()
                env_vars = [{"key": line.split("=")[0].strip(), "description": ""}
                           for line in example_text.splitlines()
                           if "=" in line and not line.startswith("#")]
            except Exception:
                env_vars = []

        if env_vars:
            db.create_env_input_card(board_id, env_vars)
            # automation spec 저장 (env 입력 대기)
            db.update_board_automation_spec(
                board_id,
                automation.get("agent_prompt", ""),
                automation.get("allowed_tools", ["Bash", "Read", "Write"]),
                str(tool_dir)
            )
            # env 입력 완료되면 스모크 테스트 (별도 엔드포인트에서 트리거)
            return

    # env 불필요하면 바로 스모크 테스트
    await _run_automation_smoke(board_id, automation, str(tool_dir))


async def _run_automation_smoke(board_id: int, automation: dict, tool_dir: str):
    """스모크 테스트: 도구 스크립트 1회 실행 확인"""
    board = db.get_board(board_id)
    if not board:
        return

    card_id = db.insert_card(board_id, "스모크 테스트 실행 중...", "in_progress", agent_role="smoke-test")

    try:
        # 간단한 스모크 테스트 — 첫 도구 스크립트 실행
        tool_scripts = list(Path(tool_dir).glob("tools/*.py"))
        if tool_scripts:
            script = str(tool_scripts[0])
            proc = await asyncio.create_subprocess_shell(
                f"cd {tool_dir} && .venv/bin/python {script}" if (Path(tool_dir) / ".venv").exists() else f"cd {tool_dir} && python {script}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
                output = stdout.decode()[:200] + stderr.decode()[:200]
                db.update_card(card_id, status="done", output=f"스모크 테스트 성공\n{output}")
            except asyncio.TimeoutError:
                db.update_card(card_id, status="error", output="스모크 테스트 타임아웃 (60초)")
                return
        else:
            db.update_card(card_id, status="done", output="스모크 테스트 완료 (도구 스크립트 없음)")

        # cron 등록
        schedule = automation.get("schedule") or board.get("cron_expr")
        if schedule:
            db.update_board_cron(board_id, schedule)
            sched.register_board(board_id, schedule)

        db.update_board_automation_spec(
            board_id,
            automation.get("agent_prompt", ""),
            automation.get("allowed_tools", ["Bash", "Read", "Write"]),
            tool_dir
        )

        try:
            await notifier.notify(
                f"[{board.get('name', 'Board')}] 자동화 준비 완료",
                f"{'스케줄: ' + schedule if schedule else '수동 트리거 준비 완료'}",
                link=f"/board/{board_id}"
            )
        except Exception:
            pass

    except Exception as e:
        logger.error("[_run_automation_smoke] Error: %s", e)
        db.update_card(card_id, status="error", output=f"스모크 테스트 실패: {str(e)[:300]}")
        try:
            await notifier.notify(
                f"[{board.get('name', '')}] 스모크 테스트 실패",
                f"자동화 설정을 확인해주세요. {str(e)[:200]}",
                link=f"/board/{board_id}"
            )
        except Exception:
            pass


async def _run_claude_for_classification(
    prompt: str,
    system_prompt: str,
    on_chunk=None,
    cwd=None,
    timeout=60,
):
    """간단한 Claude CLI 호출 (harness._run_claude와 유사하지만 더 단순)"""
    args = [
        "claude", "-p",
        "--output-format", "stream-json",
        "--input-format", "stream-json",
        "--append-system-prompt", system_prompt,
    ]

    input_payload = json.dumps({
        "type": "user",
        "message": {"role": "user", "content": prompt},
    })

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=str(cwd or Path.home()),
        )
        proc.stdin.write(input_payload.encode())
        await proc.stdin.drain()
        proc.stdin.close()

        output = ""
        async for line in proc.stdout:
            try:
                ev = json.loads(line.decode().strip())
                if ev.get("type") == "assistant":
                    for block in ev.get("message", {}).get("content", []):
                        if block.get("type") == "text":
                            chunk = block["text"]
                            output += chunk
                            if on_chunk:
                                on_chunk(chunk)
            except json.JSONDecodeError:
                pass

        await asyncio.wait_for(proc.wait(), timeout=timeout)
        return output
    except asyncio.TimeoutError:
        proc.kill()
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    _migrate_artifact_cwd()
    stuck_boards = _recover_stuck_states()
    agents_registry.get_index()
    sched.load_boards()
    # 재시작 후 stuck 보드 자동 재실행 (약간 딜레이 후)
    if stuck_boards:
        asyncio.create_task(_rerun_stuck_boards(stuck_boards))
    yield
    for proc in list(_artifact_procs.values()):
        try:
            proc.kill()
        except Exception:
            pass


async def _rerun_stuck_boards(board_ids: list):
    await asyncio.sleep(2)  # 서버 완전 기동 후 실행
    for board_id in board_ids:
        board = db.get_board(board_id)
        if not board:
            continue
        run_id = db.create_run(board_id, trigger="manual")
        logger.info("[recovery] board_%d 자동 재실행 → run_%d", board_id, run_id)
        asyncio.create_task(_run_pipeline(
            board_id, run_id, board["description"], False, board.get("project_path")
        ))


def _migrate_artifact_cwd() -> None:
    """기존 카드 중 artifact_cwd가 NULL이거나 홈 디렉터리인 것을 보드 project_path로 스냅."""
    import sqlite3 as _sql
    home = str(Path.home())
    try:
        with _sql.connect(db.DB_PATH) as conn:
            rows = conn.execute(
                "SELECT c.id, b.project_path FROM cards c JOIN boards b ON c.board_id=b.id "
                "WHERE c.run_command IS NOT NULL AND (c.artifact_cwd IS NULL OR c.artifact_cwd=?)",
                (home,),
            ).fetchall()
        for cid, pp in rows:
            if pp:
                db.update_card_artifact_cwd(cid, pp)
                logger.warning("[migrate] card_%d cwd → %s", cid, pp)
    except Exception as e:
        logger.warning("[migrate] artifact_cwd 마이그레이션 실패: %s", e)


def _recover_stuck_states() -> list:
    """서버 재시작 시 인메모리 게이트가 사라져 stuck된 board/run/card 상태를 복구.
    재실행이 필요한 board_id 목록을 반환."""
    import sqlite3 as _sqlite3
    stuck = []
    with _sqlite3.connect(db.DB_PATH) as conn:
        # 재실행 대상: generating / awaiting_project (파이프라인 중단)
        rows = conn.execute("""
            SELECT id FROM boards WHERE status IN ('generating', 'awaiting_project', 'running')
        """).fetchall()
        stuck = [r[0] for r in rows]

        conn.execute("""
            UPDATE boards SET status='ready'
            WHERE status IN ('generating', 'awaiting_project', 'running')
        """)
        conn.execute("""
            UPDATE runs SET status='error', finished_at=datetime('now')
            WHERE status IN ('generating', 'running')
        """)
        conn.execute("""
            UPDATE cards SET status='error', updated_at=datetime('now')
            WHERE status = 'in_progress'
        """)
    return stuck


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

@app.get("/api/settings/notifications")
async def get_notification_settings():
    return notifier.get_config()


@app.put("/api/settings/notifications")
async def update_notification_settings(body: dict):
    mapping = {
        "telegram_token": "notify_telegram_token",
        "telegram_chat_id": "notify_telegram_chat_id",
        "email_host": "notify_email_host",
        "email_port": "notify_email_port",
        "email_user": "notify_email_user",
        "email_pass": "notify_email_pass",
        "email_to": "notify_email_to",
    }
    for key, db_key in mapping.items():
        if key in body:
            db.set_setting(db_key, str(body[key]) if body[key] is not None else "")
    return {"ok": True}


@app.post("/api/settings/notifications/test-telegram")
async def test_telegram_notification(body: dict):
    token = body.get("token") or db.get_setting("notify_telegram_token")
    chat_id = body.get("chat_id") or db.get_setting("notify_telegram_chat_id")
    if not token or not chat_id:
        return {"ok": False, "error": "Token 또는 Chat ID가 없습니다"}
    ok = await notifier.test_telegram(token, chat_id)
    return {"ok": ok}


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

    # C-4: 동일 project_path 충돌 가드
    if project_path:
        conflicts = db.get_boards_by_project_path(project_path)
        if conflicts:
            existing_name = conflicts[0]["name"]
            logger.warning("[create_board] project_path 충돌: %s → 기존 보드 '%s'", project_path, existing_name)
            # 경고만 로깅하고 계속 진행 (사용자가 의도적으로 재사용하는 경우도 있음)

    board_id = db.create_board(
        name=user_request[:60],
        description=user_request,
        approval_mode=approval_mode,
        project_path=project_path,
        status="generating",
    )

    async def _process_board():
        """분류 → clarification/automation/build 흐름"""
        nonlocal project_path

        # Step 1: 분류
        classified = await _classify_request(user_request, project_path)
        kind = classified.get("kind", "build")

        logger.info("[create_board] board_%d classified as: %s", board_id, kind)

        if kind == "needs_clarification":
            # Clarification 흐름
            questions = classified.get("questions", [])
            db.update_board_fields(board_id, {
                "task_kind": "build",  # 아직 미확정
                "clarification_status": "pending",
                "clarification_questions": json.dumps(questions, ensure_ascii=False),
                "clarification_deadline": (asyncio.get_event_loop().time() + 86400),
            })

            run_id = db.get_latest_run_id(board_id) or db.create_run(board_id, trigger="manual")
            db.create_clarification_card(board_id, questions)

            await _board_emit(board_id, {
                "type": "status",
                "status": "awaiting_clarification",
                "questions": questions,
            })

            try:
                await notifier.notify(
                    f"[{user_request[:40]}] 정보가 필요합니다",
                    f"자동화 설정을 위해 {len(questions)}개 질문에 답변해주세요.",
                    link=f"/board/{board_id}"
                )
            except Exception:
                pass

        elif kind == "automation":
            # Automation 흐름
            db.update_board_fields(board_id, {"task_kind": "automation"})
            automation = classified.get("automation", {})
            await _provision_automation(board_id, automation, project_path or str(Path.home()))

        else:
            # Build 흐름 (기본)
            db.update_board_fields(board_id, {"task_kind": "build"})

            # project_path가 없는 글로벌 보드는 전용 디렉터리 미리 생성 후 DB에 등록
            # → LLM이 정확한 경로를 알고 artifact cwd에 올바르게 기록
            if not project_path:
                slug = re.sub(r"[^a-z0-9]+", "-", user_request[:40].lower()).strip("-")
                auto_dir = Path.home() / "Documents" / "claudeasy-projects" / f"{board_id}-{slug}"
                auto_dir.mkdir(parents=True, exist_ok=True)
                project_path = str(auto_dir)
                db.update_board_project_path(board_id, project_path)
                logger.info("[create_board] board_%d project_path 자동 할당: %s", board_id, project_path)

            # 분류 오판 안전망: 스케줄 키워드가 있으면 cron 자동 등록
            _auto_cron = _parse_schedule_intent(user_request)
            if _auto_cron:
                db.update_board_cron(board_id, _auto_cron)
                sched.register_board(board_id, _auto_cron)
                try:
                    await notifier.notify(
                        user_request[:40],
                        f"스케줄을 자동 등록했습니다 ({_auto_cron}). 변경하려면 스케줄 메뉴에서 수정하세요.",
                        link=f"/board/{board_id}",
                    )
                except Exception:
                    pass
            run_id = db.create_run(board_id, trigger="manual")

            if source_type == "github" and github_repo and github_installation_id:
                db.update_board_github(board_id, github_repo, int(github_installation_id), github_ref)
                try:
                    board = db.get_board(board_id)
                    resolved = await _resolve_board_workspace(board)
                    await _run_pipeline(board_id, run_id, user_request, use_tavily, str(resolved))
                except Exception as exc:
                    db.update_run_status(run_id, "error")
                    db.update_board_status(board_id, "error")
                    logger.error("[create_board] github clone failed: %s", exc)
            else:
                await _run_pipeline(board_id, run_id, user_request, use_tavily, project_path)

    asyncio.create_task(_process_board())
    return {"board_id": board_id, **db.get_board(board_id)}


@app.post("/api/boards/{board_id}/runs")
async def rerun_board(board_id: int, body: dict = {}):
    """기존 보드를 새 run으로 재실행"""
    board = db.get_board(board_id)
    if not board:
        return {"error": "보드를 찾을 수 없습니다"}

    run_id = db.create_run(board_id, trigger="rerun")
    if board.get("task_kind") == "automation":
        asyncio.create_task(_execute_automation_run(board_id, run_id, board))
    else:
        asyncio.create_task(_run_pipeline(
            board_id, run_id, board["description"], False, board.get("project_path")
        ))
    return {"board_id": board_id, "run_id": run_id}


@app.post("/api/boards/{board_id}/clarification")
async def submit_clarification(board_id: int, body: dict):
    """clarification 답변 제출"""
    board = db.get_board(board_id)
    if not board:
        return {"error": "보드를 찾을 수 없습니다"}

    answers = body.get("answers", {})

    db.save_clarification_answers(board_id, answers)

    # 질문+답변 컨텍스트 붙여서 orchestrator 재호출
    questions = []
    try:
        questions = json.loads(board.get("clarification_questions") or "[]")
    except Exception:
        pass

    qa_context = "\n".join([
        f"Q: {q['question']}\nA: {answers.get(q['id'], '(미응답)')}"
        for q in questions
    ])
    enriched_title = f"{board['description']}\n\n[추가 정보]\n{qa_context}"

    # clarification 시도 횟수 체크 (무한루프 방지, 최대 3회)
    attempt = (board.get("clarification_attempt") or 0) + 1
    db.update_board_fields(board_id, {"clarification_attempt": attempt})

    if attempt >= 3:
        # 강제 build 폴백
        db.update_board_fields(board_id, {"task_kind": "build", "clarification_status": "resolved"})
        run_id = db.create_run(board_id, trigger="manual")
        asyncio.create_task(_run_pipeline(board_id, run_id, enriched_title, False, board.get("project_path", "")))
        return {"status": "ok", "kind": "build"}

    classified = await _classify_request(enriched_title, board.get("project_path", ""))

    if classified.get("kind") == "needs_clarification":
        new_questions = classified.get("questions", [])
        db.update_board_fields(board_id, {
            "clarification_status": "pending",
            "clarification_questions": json.dumps(new_questions, ensure_ascii=False),
        })
        db.create_clarification_card(board_id, new_questions)
        return {"status": "ok", "kind": "needs_clarification", "questions": new_questions}

    elif classified.get("kind") == "automation":
        db.update_board_fields(board_id, {"task_kind": "automation", "clarification_status": "resolved"})
        automation = classified.get("automation", {})
        asyncio.create_task(_provision_automation(board_id, automation, board.get("project_path", "")))
        return {"status": "ok", "kind": "automation"}

    else:
        db.update_board_fields(board_id, {"task_kind": "build", "clarification_status": "resolved"})
        # 분류 오판 안전망: 스케줄 키워드가 있으면 cron 자동 등록
        _auto_cron = _parse_schedule_intent(enriched_title)
        if _auto_cron:
            db.update_board_cron(board_id, _auto_cron)
            sched.register_board(board_id, _auto_cron)
            try:
                await notifier.notify(
                    board.get("name", board["description"][:40]),
                    f"스케줄을 자동 등록했습니다 ({_auto_cron}). 변경하려면 스케줄 메뉴에서 수정하세요.",
                    link=f"/board/{board_id}",
                )
            except Exception:
                pass
        run_id = db.create_run(board_id, trigger="manual")
        asyncio.create_task(_run_pipeline(board_id, run_id, enriched_title, False, board.get("project_path", "")))
        return {"status": "ok", "kind": "build"}


@app.post("/api/boards/{board_id}/env")
async def save_board_env(board_id: int, body: dict):
    """automation 환경 변수 저장 후 스모크 테스트"""
    board = db.get_board(board_id)
    if not board:
        return {"error": "보드를 찾을 수 없습니다"}

    tool_dir = board.get("automation_tool_dir")
    if not tool_dir:
        return {"error": "automation_tool_dir not set"}

    env_path = Path(tool_dir) / ".env"
    lines = [f"{k}={v}" for k, v in body.items() if k and v]
    env_path.write_text("\n".join(lines) + "\n")
    env_path.chmod(0o600)

    # env_input 카드 완료 처리
    import sqlite3
    with sqlite3.connect(db.DB_PATH) as c:
        c.execute("UPDATE cards SET status='done' WHERE board_id=? AND card_kind='env_input'", (board_id,))

    # automation spec 확인
    board = db.get_board(board_id)
    if not board.get("automation_agent_prompt"):
        return {"error": "automation spec not set"}

    automation = {
        "agent_prompt": board["automation_agent_prompt"],
        "allowed_tools": json.loads(board.get("automation_allowed_tools") or '["Bash","Read","Write"]'),
        "schedule": board.get("cron_expr"),
    }
    asyncio.create_task(_run_automation_smoke(board_id, automation, tool_dir))
    return {"status": "ok"}


@app.get("/api/boards/{board_id}/automation")
async def get_automation_info(board_id: int):
    """automation 보드의 tool_dir, 스크립트 목록, cron_expr 반환."""
    board = db.get_board(board_id)
    if not board:
        return {"error": "not found"}
    tool_dir = board.get("automation_tool_dir") or board.get("project_path", "")
    scripts: list[str] = []
    if tool_dir:
        scripts = [p.name for p in sorted(Path(tool_dir).glob("tools/*.py")) if p.is_file()]
    return {
        "task_kind": board.get("task_kind"),
        "tool_dir": tool_dir,
        "scripts": scripts,
        "cron_expr": board.get("cron_expr"),
    }


@app.get("/api/boards/{board_id}/topic-queue")
async def get_topic_queue(board_id: int):
    board = db.get_board(board_id)
    if not board or not board.get("project_path"):
        return JSONResponse(status_code=404, content={"error": "project_path 없음"})
    qf = Path(board["project_path"]) / "topic_queue.json"
    if not qf.exists():
        return JSONResponse(status_code=404, content={"error": "topic_queue.json 없음"})
    try:
        return json.loads(qf.read_text(encoding="utf-8"))
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/boards/{board_id}/topic-queue/init")
async def init_topic_queue(board_id: int):
    """topic_queue.json이 없는 보드에 빈 큐 파일을 생성해 큐 관리 UI를 활성화."""
    board = db.get_board(board_id)
    if not board or not board.get("project_path"):
        return JSONResponse(status_code=400, content={"error": "project_path가 설정되지 않은 보드입니다"})
    pp = Path(board["project_path"])
    if not pp.exists():
        return JSONResponse(status_code=400, content={"error": f"프로젝트 디렉터리 없음: {pp}"})
    qf = pp / "topic_queue.json"
    if not qf.exists():
        qf.write_text(json.dumps({"queue": [], "history": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True}


@app.post("/api/boards/{board_id}/topic-queue")
async def add_topic_queue(board_id: int, request: Request):
    board = db.get_board(board_id)
    if not board or not board.get("project_path"):
        return JSONResponse(status_code=404, content={"error": "project_path 없음"})
    qf = Path(board["project_path"]) / "topic_queue.json"
    data = json.loads(qf.read_text(encoding="utf-8")) if qf.exists() else {"queue": [], "history": []}
    item = await request.json()
    if not item.get("value", "").strip():
        return JSONResponse(status_code=400, content={"error": "value 필요"})
    item.setdefault("type", "topic")
    data["queue"].append(item)
    qf.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "queue": data["queue"]}


@app.delete("/api/boards/{board_id}/topic-queue/{index}")
async def delete_topic_queue_item(board_id: int, index: int):
    board = db.get_board(board_id)
    if not board or not board.get("project_path"):
        return JSONResponse(status_code=404, content={"error": "project_path 없음"})
    qf = Path(board["project_path"]) / "topic_queue.json"
    if not qf.exists():
        return JSONResponse(status_code=404, content={"error": "topic_queue.json 없음"})
    data = json.loads(qf.read_text(encoding="utf-8"))
    if 0 <= index < len(data["queue"]):
        data["queue"].pop(index)
        qf.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "queue": data["queue"]}


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
async def delete_board(board_id: int, delete_files: bool = False):
    board = db.get_board(board_id)
    sched.unregister_board(board_id)
    db.delete_board(board_id)

    deleted_path = None
    if delete_files and board and board.get("project_path"):
        p = Path(board["project_path"])
        if p.exists() and p.is_dir():
            if _safe_rmtree(p):
                deleted_path = str(p)
            else:
                logger.warning("[delete_board] rmtree 거부 — 허용 외 경로: %s", p)

    return {"ok": True, "deleted_path": deleted_path}


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


async def _execute_automation_run(board_id: int, run_id: int, board: dict) -> None:
    """자동화 보드의 tool 스크립트를 실행하고 결과를 카드/run에 기록."""
    tool_dir = board.get("automation_tool_dir") or board.get("project_path", "")

    if not board.get("automation_agent_prompt"):
        logger.error("Board %d: automation_agent_prompt is not set", board_id)
        return

    db.update_board_status(board_id, "running")
    await _board_emit(board_id, {"type": "status", "status": "running", "run_id": run_id})

    try:
        tool_scripts = sorted(Path(tool_dir).glob("tools/*.py"))
        all_outputs = []

        for script_path in tool_scripts:
            card_id = db.insert_card(board_id, f"자동화: {script_path.stem}", "in_progress")
            try:
                python_bin = ".venv/bin/python" if (Path(tool_dir) / ".venv").exists() else "python"
                proc = await asyncio.create_subprocess_exec(
                    python_bin, str(script_path),
                    cwd=tool_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
                output = stdout.decode()[:1000] + stderr.decode()[:500]
                db.update_card(card_id, status="done", output=output)
                all_outputs.append(f"### {script_path.stem}\n{output}")
            except Exception as e:
                output = f"Error: {str(e)[:300]}"
                db.update_card(card_id, status="error", output=output)
                all_outputs.append(f"### {script_path.stem}\n{output}")

        db.update_run_status(run_id, "done")
        db.update_board_status(board_id, "done")
        await _board_emit(board_id, {"type": "status", "status": "done", "run_id": run_id})

        combined = "\n\n".join(all_outputs) if all_outputs else "자동화 실행 완료"
        try:
            await notifier.notify(board.get("name", "Board"), combined, link=f"/board/{board_id}")
        except Exception:
            pass

    except Exception as e:
        logger.error("Automation failed for board %d: %s", board_id, e)
        db.update_run_status(run_id, "error")
        db.update_board_status(board_id, "error")
        try:
            await notifier.notify(
                board.get("name", "Board"),
                f"자동화 실행 실패: {str(e)[:200]}",
                link=f"/board/{board_id}",
            )
        except Exception:
            pass


@app.post("/api/boards/{board_id}/schedule/trigger")
async def trigger_now(board_id: int):
    board = db.get_board(board_id)
    if not board:
        return {"error": "not found"}

    task_kind = board.get("task_kind", "build")
    run_id = db.create_run(board_id, trigger="cron")

    async def _trigger():
        # 자동화 보드 처리
        if task_kind == "automation":
            await _execute_automation_run(board_id, run_id, board)
            return

        # 빌드 보드 처리
        prev_run_id = db.get_latest_run_id(board_id)
        prev_cards = db.get_cards_for_run(prev_run_id) if prev_run_id else []

        # 스크립트 카드 찾기 (run_command 있는 것)
        script_cards = [c for c in prev_cards if c.get("run_command")]

        async def _run_build():
            if not prev_cards:
                # 최초 실행 — 아직 개발 안 됨, 파이프라인 새로 생성
                try:
                    workspace = await _resolve_board_workspace(board)
                    project_path = str(workspace) if workspace else board.get("project_path")
                except Exception as exc:
                    logger.error("[trigger_now] workspace resolve failed: %s", exc)
                    project_path = board.get("project_path")
                await _run_pipeline(board_id, run_id, board["description"], False, project_path)
                return

            if not script_cards:
                # 파이프라인 없이 단순 재실행 불가
                logger.warning(f"Board {board_id}: no script artifacts, skipping trigger")
                db.update_run_status(run_id, "error")
                try:
                    await notifier.notify(board.get("name", "Board"), "실행 가능한 artifact가 없습니다. 먼저 개발을 완료해주세요.", link=f"/board/{board_id}")
                except Exception:
                    pass
                return

            db.update_board_status(board_id, "running")
            await _board_emit(board_id, {"type": "status", "status": "running", "run_id": run_id})

            all_outputs = []
            # 스크립트 실행
            for card in script_cards:
                cwd = card.get("artifact_cwd") or board.get("project_path")
                if not cwd or not Path(cwd).exists():
                    logger.warning("[trigger_now] card_%d cwd 부재: %s — 스킵", card["id"], cwd)
                    all_outputs.append(f"[오류] cwd 부재: {cwd}")
                    continue
                cmd = card["run_command"]
                logger.info("[trigger_now] board_%d 스크립트 실행: %s", board_id, cmd)
                try:
                    proc = await asyncio.create_subprocess_shell(
                        cmd, cwd=cwd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT,
                    )
                    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
                    output = stdout.decode("utf-8", errors="replace").strip()
                except asyncio.TimeoutError:
                    output = "[오류] 실행 시간 초과 (5분)"
                except Exception as e:
                    output = f"[오류] {e}"

                new_card_id = db.create_card(
                    board_id, run_id,
                    title=card["title"],
                    description=card["description"],
                    agent_role=card["agent_role"],
                )
                db.append_card_output(new_card_id, output)
                db.update_card_status(new_card_id, "done")
                all_outputs.append(f"### {card['title']}\n{output}")

            db.update_run_status(run_id, "done")
            db.update_board_status(board_id, "done")
            await _board_emit(board_id, {"type": "status", "status": "done", "run_id": run_id})

            combined = "\n\n".join(all_outputs)
            try:
                await notifier.notify(board.get("name", "Board"), combined, link=f"/board/{board_id}")
            except Exception:
                pass

        await _run_build()

    asyncio.create_task(_trigger())
    return {"board_id": board_id, "run_id": run_id}


# ── Feedback ──────────────────────────────────────────────────────────────────

def _parse_schedule_intent(text: str):
    """자연어에서 스케줄 의도와 cron 표현식을 추출.
    스케줄 의도가 없으면 None 반환."""
    import re
    t = text.strip()

    SCHEDULE_KEYWORDS = [
        "스케줄", "schedule", "매일", "매주", "매월", "마다", "마다 실행",
        "주기적", "자동 실행", "자동실행", "반복", "cron", "크론",
        "시에 실행", "분마다", "시간마다", "일마다",
    ]
    if not any(kw in t.lower() for kw in SCHEDULE_KEYWORDS):
        return None

    # 매일 HH:MM
    m = re.search(r"매일\s+(?:오전|오후)?\s*(\d{1,2})(?::(\d{2}))?", t)
    if m:
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if "오후" in t and h < 12:
            h += 12
        return f"{mi} {h} * * *"

    # 매주 요일 HH:MM
    DOW = {"월": 1, "화": 2, "수": 3, "목": 4, "금": 5, "토": 6, "일": 0}
    m = re.search(r"매주\s+([월화수목금토일])요일?\s+(?:오전|오후)?\s*(\d{1,2})(?::(\d{2}))?", t)
    if m:
        dow = DOW.get(m.group(1), 1)
        h, mi = int(m.group(2)), int(m.group(3) or 0)
        if "오후" in t and h < 12:
            h += 12
        return f"{mi} {h} * * {dow}"

    # N분마다
    m = re.search(r"(\d+)\s*분\s*마다", t)
    if m:
        n = int(m.group(1))
        if n < 60:
            return f"*/{n} * * * *"
        return f"0 */{n // 60} * * *"

    # N시간마다
    m = re.search(r"(\d+)\s*시간\s*마다", t)
    if m:
        n = int(m.group(1))
        return f"0 */{n} * * *"

    # 매시 N분
    m = re.search(r"매시\s*(?:정각|(\d+)분)?", t)
    if m:
        mi = int(m.group(1)) if m.group(1) else 0
        return f"{mi} * * * *"

    # 숫자만 있는 cron 표현식 직접 입력
    m = re.search(r"(\d[\d\s*/,-]+\d)", t)
    if m:
        candidate = m.group(1).strip()
        if len(candidate.split()) == 5:
            return candidate

    return None


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
    elif ftype == "comment" and content.strip():
        # 스케줄 요청 감지
        cron_expr = _parse_schedule_intent(content)
        if cron_expr:
            card = db.get_card(card_id)
            if card:
                board_id = card["board_id"]
                db.update_board_cron(board_id, cron_expr)
                sched.register_board(board_id, cron_expr)
                next_run = sched.get_next_run_time(board_id)
                next_str = f" (다음 실행: {next_run})" if next_run else ""
                confirm_msg = f"스케줄 등록됨: `{cron_expr}`{next_str}"
                feedback_id = db.add_feedback(card_id, "comment", content, parent_id=parent_id)
                db.add_feedback(card_id, "agent_reply", confirm_msg, author="system", parent_id=feedback_id)
                run_id = card["run_id"]
                await _card_emit(card_id, {"type": "feedback_update", "feedback_id": feedback_id})
                await _run_emit(run_id, {"type": "feedback_update", "card_id": card_id})
                await _board_emit(board_id, {"type": "feedback_update", "card_id": card_id, "run_id": run_id})
                return {"ok": True, "schedule_set": True, "cron_expr": cron_expr}
        db.add_feedback(card_id, ftype, content, parent_id=parent_id)
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

def _find_free_port(preferred: int = None, start: int = 8200, end: int = 8900) -> int:
    import socket
    candidates = ([preferred] if preferred else []) + list(range(start, end))
    for port in candidates:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start


def _inject_port(cmd: str, old_port: int, new_port: int) -> str:
    """run_command 내 포트 번호를 교체. 단어 경계로 한정해 오탐 방지."""
    import re
    if old_port and old_port != new_port:
        return re.sub(r'(?<!\d)' + str(old_port) + r'(?!\d)', str(new_port), cmd)
    return cmd


def _safe_rmtree(path: Path) -> bool:
    """허용된 경로 내부일 때만 rmtree를 실행. 홈 디렉터리 등 위험 경로는 거부."""
    import shutil
    safe_roots = [
        Path.home() / "Documents",
        Path.home() / ".claude-local-workspaces",
        Path("/tmp"),
    ]
    try:
        resolved = path.resolve()
    except Exception:
        return False
    for root in safe_roots:
        try:
            if resolved.is_relative_to(root.resolve()) and resolved != root.resolve():
                shutil.rmtree(resolved)
                return True
        except Exception:
            continue
    logger.warning("[_safe_rmtree] 거부: %s 는 허용 경로 외부", resolved)
    return False


def _script_missing(cmd: str, cwd: "str | None") -> "str | None":
    """run_command에서 파일 실재를 검사할 수 있는 패턴만 확인. 없으면 None 반환(검증 패스)."""
    import shlex, json as _json
    if not cwd:
        return None
    base = Path(cwd)
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return None
    if len(tokens) < 2:
        return None
    # python3 X.py / node X.js / tsx X.ts / bun X.ts
    if tokens[0] in ("python3", "python", "node", "tsx", "ts-node", "bun") and tokens[1].endswith(
        (".py", ".js", ".ts", ".mjs")
    ):
        target = base / tokens[1]
        if not target.exists():
            return tokens[1]
    # npm/pnpm/yarn run X → package.json + scripts.X 존재 확인
    if tokens[0] in ("npm", "pnpm", "yarn") and len(tokens) >= 3 and tokens[1] == "run":
        pkg = base / "package.json"
        if not pkg.exists():
            return "package.json"
        try:
            scripts = _json.loads(pkg.read_text()).get("scripts", {})
            if tokens[2] not in scripts:
                return f"npm script '{tokens[2]}'"
        except Exception:
            pass
    return None


async def _watch_early_exit(card_id: int, proc: asyncio.subprocess.Process) -> None:
    """5초 내 비정상 종료 시 stderr tail을 WS + 카드 output에 기록."""
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except asyncio.TimeoutError:
        return  # 5초 생존 = 정상 기동
    if proc.returncode == 0:
        _artifact_procs.pop(card_id, None)
        _artifact_watchers.pop(card_id, None)
        return
    tail = b""
    if proc.stderr:
        try:
            tail = await asyncio.wait_for(proc.stderr.read(4096), timeout=1)
        except Exception:
            pass
    tail_str = tail.decode("utf-8", "replace").strip()[-2000:]
    marker = f"\n\n---\n**[실행 실패 rc={proc.returncode}]**\n```\n{tail_str}\n```"
    db.append_card_output(card_id, marker)
    await _card_emit(card_id, {
        "type": "artifact_failed",
        "rc": proc.returncode,
        "stderr_tail": tail_str,
    })
    _artifact_procs.pop(card_id, None)
    _artifact_watchers.pop(card_id, None)


async def _persist_card_artifact(
    card_id: int, artifact: "dict | None", project_path: "str | None"
) -> "dict | None":
    """artifact 검증 → DB 저장 → 경고 마커 부착. 공용 게이트 (3개 호출처 공유)."""
    if not artifact:
        return None
    warnings = artifact.pop("_warnings", [])
    cmd = artifact.get("run_command", "").strip()
    cwd = artifact.get("cwd") or project_path

    # Hard gate: 저장 자체를 거부해 실행 버튼 미노출
    def _reject(reason: str) -> None:
        db.append_card_output(card_id, f"\n\n---\n**[artifact 미저장]**\n- {reason}\n")
        logger.warning("[artifact gate] card_%d 거부: %s", card_id, reason)

    if not cmd:
        _reject("run_command 비어있음")
        return None
    if cwd and not Path(cwd).exists():
        _reject(f"cwd 부재: {cwd}")
        return None
    miss = _script_missing(cmd, cwd)
    if miss:
        _reject(f"스크립트 부재: {miss}")
        return None

    db.update_card_artifact(card_id, artifact["type"], cmd, artifact.get("port"), cwd)

    # 보드 project_path 자동 채우기 — null이면 artifact cwd로 설정
    card_row = db.get_card(card_id)
    if card_row and card_row.get("board_id") and cwd:
        _board = db.get_board(card_row["board_id"])
        if _board and not _board.get("project_path"):
            db.update_board_project_path(card_row["board_id"], cwd)
            logger.info("[project_path] board_%d → %s", card_row["board_id"], cwd)

    # SDK 자동 교체 — 프로젝트 파일에서 'import anthropic' 등 제거
    sdk_fixed = _sanitize_sdk_usage(project_path)
    if sdk_fixed:
        sdk_warn = f"SDK 자동 교체됨: {', '.join(sdk_fixed)}"
        warnings.append(sdk_warn)
        logger.warning("[sdk-sanitize] card_%d %s", card_id, sdk_warn)

    if warnings:
        marker = "\n\n---\n**[artifact 검증 경고]**\n" + "".join(f"- {w}\n" for w in warnings)
        db.append_card_output(card_id, marker)
        await _card_emit(card_id, {"type": "artifact_warning", "warnings": warnings})
    return artifact


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
    # 기존 watcher cancel
    old_w = _artifact_watchers.pop(card_id, None)
    if old_w:
        old_w.cancel()

    # cwd 결정 — home() fallback 제거, project_path 우선
    board = db.get_board(card.get("board_id")) if card.get("board_id") else None
    cwd = card.get("artifact_cwd") or (board.get("project_path") if board else None)
    if not cwd or not Path(cwd).exists():
        return {"error": f"실행 디렉터리를 찾을 수 없습니다: {cwd}"}

    cmd_raw = card["run_command"]
    miss = _script_missing(cmd_raw, cwd)
    if miss:
        return {"error": f"스크립트가 존재하지 않습니다: {miss}"}

    preferred_port = card.get("artifact_port")
    actual_port = _find_free_port(preferred_port)
    cmd = _inject_port(cmd_raw, preferred_port, actual_port)

    if actual_port != preferred_port:
        db.update_card_artifact(card_id, card.get("artifact_type"), cmd, actual_port, cwd)
        logger.info("[run_artifact] 포트 충돌 → %d → %d 사용", preferred_port, actual_port)

    import copy
    proc_env = copy.copy(os.environ)
    env_file = Path(cwd) / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                if k.strip() and v.strip():
                    proc_env[k.strip()] = v.strip()

    new_proc = await asyncio.create_subprocess_shell(
        cmd, cwd=cwd,
        env=proc_env,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,  # early-exit watcher가 읽음
    )
    _artifact_procs[card_id] = new_proc
    _artifact_watchers[card_id] = asyncio.create_task(
        _watch_early_exit(card_id, new_proc)
    )
    await _card_emit(card_id, {"type": "artifact_started", "pid": new_proc.pid, "port": actual_port})
    return {"pid": new_proc.pid, "port": actual_port}


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
    w = _artifact_watchers.pop(card_id, None)
    if w:
        w.cancel()
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


# ── Artifact Env ─────────────────────────────────────────────────────────────

@app.get("/api/cards/{card_id}/env-vars")
async def get_artifact_env_vars(card_id: int):
    """.env.example 파싱 → 현재 .env 값(마스킹) 포함해 반환"""
    card = db.get_card(card_id)
    if not card or not card.get("artifact_cwd"):
        return {"vars": []}

    cwd = Path(card["artifact_cwd"])
    example_path = cwd / ".env.example"
    env_path = cwd / ".env"

    if not example_path.exists():
        return {"vars": []}

    # .env.example 파싱
    vars_list = []
    for line in example_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            description = line.lstrip("# ").strip() if line.startswith("#") else ""
            continue
        if "=" in line:
            key = line.split("=")[0].strip()
            vars_list.append({"key": key, "description": "", "has_value": False})

    # .env 파일에서 값 유무 확인
    existing_keys: set[str] = set()
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                if v.strip():
                    existing_keys.add(k.strip())

    # 서버 프로세스 환경변수도 확인 (부모 env 상속 → 별도 입력 불필요)
    for v in vars_list:
        v["has_value"] = v["key"] in existing_keys or bool(os.environ.get(v["key"]))
        v["from_env"] = bool(os.environ.get(v["key"])) and v["key"] not in existing_keys

    return {"vars": vars_list}


@app.post("/api/cards/{card_id}/env")
async def save_artifact_env(card_id: int, body: dict):
    """{key: value} 를 artifact_cwd/.env 에 머지 저장"""
    card = db.get_card(card_id)
    if not card or not card.get("artifact_cwd"):
        return {"error": "artifact_cwd not set"}

    cwd = Path(card["artifact_cwd"])
    cwd.mkdir(parents=True, exist_ok=True)
    env_path = cwd / ".env"

    # 기존 .env 읽기
    existing: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip()

    # 새 값 머지
    existing.update({k: v for k, v in body.items() if k and v})

    lines = [f"{k}={v}" for k, v in existing.items()]
    env_path.write_text("\n".join(lines) + "\n")
    env_path.chmod(0o600)
    return {"ok": True, "written": len(lines)}


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
                     "design_system": c.get("design_system"),
                     "depends_on": json.loads(c["depends_on"]) if c.get("depends_on") else None}
                    for c in prev_cards if c["status"] != "rejected"
                ]
            else:
                tasks = [{"title": user_request[:60], "description": user_request,
                          "agent": existing_agent_names[0] if existing_agent_names else "assistant",
                          "depends_on": None}]
        else:
            tasks = parsed.get("tasks") or [{"title": user_request[:60], "description": user_request,
                                              "agent": agents[0]["name"] if agents else "assistant",
                                              "depends_on": None}]

        # ── cards 생성 (run 레벨) ────────────────────────────────────────────
        card_ids = []
        for t in tasks:
            cid = db.create_card(board_id, run_id, t.get("title", ""), t.get("description", ""),
                                 t.get("agent", ""), t.get("design_system"), t.get("depends_on"))
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

        async def _run_cards_with_deps(card_ids: list, tasks: list, run_fn):
            """의존성 그래프 기반 실행.
            - 사이클 감지 (위상 정렬): 순환 의존 카드는 error로 마킹하고 건너뜀.
            - 실패 전파: 부모 카드가 error/rejected면 자식은 blocked(error)로 처리.
            - 부분 deps: depends_on이 하나라도 있으면 graph 모드, 없는 카드는 직전 카드를 암묵적 의존으로 처리.
            """
            n = len(tasks)
            failed = [False] * n  # 실패/차단 여부 추적
            events = [asyncio.Event() for _ in range(n)]
            has_dep_info = any(t.get("depends_on") is not None for t in tasks)

            # 사이클 검사 (Kahn's algorithm)
            if has_dep_info:
                in_degree = [0] * n
                adj = [[] for _ in range(n)]
                for i, t in enumerate(tasks):
                    for dep_idx in (t.get("depends_on") or []):
                        if 0 <= dep_idx < n:
                            adj[dep_idx].append(i)
                            in_degree[i] += 1
                queue = [i for i in range(n) if in_degree[i] == 0]
                visited_count = 0
                while queue:
                    v = queue.pop()
                    visited_count += 1
                    for u in adj[v]:
                        in_degree[u] -= 1
                        if in_degree[u] == 0:
                            queue.append(u)
                if visited_count < n:
                    # 순환 의존 감지
                    for i, cid in enumerate(card_ids):
                        if in_degree[i] > 0:
                            db.update_card_status(cid, "error")
                            db.append_card_output(cid, "\n\n**[오류]** 순환 의존이 감지되어 실행이 중단되었습니다.")
                            failed[i] = True
                            events[i].set()
                    logger.error("[deps] 순환 의존 감지 — board %s", board_id)

            async def run_one(i):
                if failed[i]:
                    return
                deps = tasks[i].get("depends_on")
                if not has_dep_info:
                    # 구형 카드: 순차 실행
                    if i > 0:
                        await events[i - 1].wait()
                        if failed[i - 1]:
                            failed[i] = True
                            db.update_card_status(card_ids[i], "error")
                            db.append_card_output(card_ids[i], "\n\n**[차단됨]** 선행 카드가 실패해 실행이 건너뛰어졌습니다.")
                            events[i].set()
                            return
                else:
                    # graph 모드: deps 없으면 즉시 실행 (의도적 병렬), 있으면 대기
                    for dep_idx in (deps or []):
                        if 0 <= dep_idx < n:
                            await events[dep_idx].wait()
                            if failed[dep_idx]:
                                failed[i] = True
                                db.update_card_status(card_ids[i], "error")
                                db.append_card_output(card_ids[i], f"\n\n**[차단됨]** 선행 카드(#{dep_idx + 1})가 실패해 실행이 건너뛰어졌습니다.")
                                events[i].set()
                                return

                await run_fn(card_ids[i], tasks[i])

                # 실행 후 실제 결과 확인 (run_fn이 예외를 삼킬 수 있으므로)
                final_status = (db.get_card(card_ids[i]) or {}).get("status")
                if final_status in ("error", "rejected"):
                    failed[i] = True

                events[i].set()

            await asyncio.gather(*[run_one(i) for i in range(n)])

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
                # artifact 파싱 → 검증·보정 → DB 저장
                _final_card = db.get_card(card_id)
                _artifact = await _persist_card_artifact(
                    card_id,
                    parse_artifact(_final_card.get("output") or "", project_path),
                    project_path,
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

        await _run_cards_with_deps(card_ids, tasks, _run_single_card)

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
        # artifact 파싱 → 검증·보정 → DB 저장 (H-10 재실행 경로 포함)
        _rerun_card_data = db.get_card(card_id)
        _rerun_artifact = await _persist_card_artifact(
            card_id,
            parse_artifact(_rerun_card_data.get("output") or "", board.get("project_path")),
            board.get("project_path"),
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


_SENSITIVE_QUESTION_RE = re.compile(
    r"password|비밀번호|로그인\s*계정|api[_\s]*key|토큰|token"
    r"|신용\s*카드|card\s*number|ssn|주민\s*등록|secret|credential|otp|2fa",
    re.IGNORECASE,
)


def _is_sensitive_question(text: str) -> bool:
    return bool(_SENSITIVE_QUESTION_RE.search(text))


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

    board_id = card["board_id"]
    run_id   = card["run_id"]

    # 민감 정보 질문 감지 시 자동 답변 차단
    if _is_sensitive_question(output):
        _auto_answer_counts[card_id] = _auto_answer_counts.get(card_id, 0) + 1
        db.update_card_status(card_id, "awaiting_clarification")
        await _card_emit(card_id, {"type": "awaiting_clarification", "reason": "sensitive"})
        await _board_emit(board_id, {"type": "card_update", "card_id": card_id,
                                     "status": "awaiting_clarification", "run_id": run_id})
        try:
            await notifier.notify(
                board.get("name", "Board"),
                "민감 정보 답변이 필요해 자동 응답을 중단했습니다. 카드를 확인해주세요.",
                link=f"/board/{board_id}",
            )
        except Exception:
            pass
        return

    _auto_answer_counts[card_id] = _auto_answer_counts.get(card_id, 0) + 1

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
