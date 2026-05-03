"""SQLite — boards, runs, cards, agents, feedback"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data.db"


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS boards (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            description   TEXT,
            cron_expr     TEXT,
            approval_mode TEXT DEFAULT 'auto',  -- auto | manual
            project_path  TEXT,                  -- 연결된 프로젝트 경로 (null=HOME)
            status        TEXT DEFAULT 'generating',
            created_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            board_id    INTEGER REFERENCES boards(id),
            status      TEXT DEFAULT 'generating',  -- generating | ready | running | done | error
            session_id  TEXT,
            trigger     TEXT DEFAULT 'manual',       -- manual | cron | rerun
            created_at  TEXT DEFAULT (datetime('now')),
            finished_at TEXT
        );

        CREATE TABLE IF NOT EXISTS cards (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            board_id    INTEGER REFERENCES boards(id),
            run_id      INTEGER REFERENCES runs(id),
            title       TEXT NOT NULL,
            description TEXT,
            status      TEXT DEFAULT 'backlog',  -- backlog | awaiting_approval | in_progress | done | error | rejected
            agent_role  TEXT,
            output      TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS agents (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            board_id INTEGER REFERENCES boards(id),
            name     TEXT NOT NULL,
            role     TEXT,
            color    TEXT DEFAULT '#6366f1',
            status   TEXT DEFAULT 'idle'  -- idle | working
        );

        CREATE TABLE IF NOT EXISTS feedback (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id    INTEGER REFERENCES cards(id),
            type       TEXT NOT NULL,  -- approve | reject | comment | rerun | agent_reply
            content    TEXT,
            author     TEXT DEFAULT 'user',  -- 'user' | agent name
            parent_id  INTEGER REFERENCES feedback(id),
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        """)

        # 기존 DB 마이그레이션 (컬럼 누락 시 추가)
        _migrate(conn)

        # 기존 cards에 run_id 없는 경우: board별 Run #1 자동 생성
        _migrate_legacy_cards(conn)


def _safe_alter(sql: str):
    """안전한 ALTER TABLE 실행 — 실패 시 무시"""
    try:
        with sqlite3.connect(DB_PATH) as c:
            c.execute(sql)
    except sqlite3.OperationalError:
        pass  # column already exists


def _migrate(conn):
    """기존 스키마에 새 컬럼 추가"""
    migrations = [
        "ALTER TABLE boards ADD COLUMN status TEXT DEFAULT 'generating'",
        "ALTER TABLE boards ADD COLUMN cron_expr TEXT",
        "ALTER TABLE boards ADD COLUMN approval_mode TEXT DEFAULT 'auto'",
        "ALTER TABLE boards ADD COLUMN project_path TEXT",
        "ALTER TABLE cards ADD COLUMN run_id INTEGER",
        "ALTER TABLE cards ADD COLUMN board_id INTEGER",
        # boards의 session_id는 runs로 이전 — boards 테이블에서 제거 안 함 (하위호환)
        "ALTER TABLE boards ADD COLUMN session_id TEXT",
        # 카드별 독립 세션 (병렬 실행 지원)
        "ALTER TABLE cards ADD COLUMN session_id TEXT",
        # 피드백 스레딩
        "ALTER TABLE feedback ADD COLUMN author TEXT DEFAULT 'user'",
        "ALTER TABLE feedback ADD COLUMN parent_id INTEGER",
        "ALTER TABLE cards ADD COLUMN artifact_type TEXT",
        "ALTER TABLE cards ADD COLUMN run_command TEXT",
        "ALTER TABLE cards ADD COLUMN artifact_port INTEGER",
        "ALTER TABLE cards ADD COLUMN artifact_cwd TEXT",
        "ALTER TABLE cards ADD COLUMN design_system TEXT",
        # GitHub App 연동
        "ALTER TABLE boards ADD COLUMN source_type TEXT DEFAULT 'local'",
        "ALTER TABLE boards ADD COLUMN github_repo TEXT",
        "ALTER TABLE boards ADD COLUMN github_installation_id INTEGER",
        "ALTER TABLE boards ADD COLUMN github_ref TEXT DEFAULT 'main'",
        "ALTER TABLE boards ADD COLUMN github_last_sha TEXT",
        "ALTER TABLE boards ADD COLUMN workspace_path TEXT",
        # Orchestration Engine 신규 컬럼
        "ALTER TABLE boards ADD COLUMN task_kind TEXT DEFAULT 'build'",
        "ALTER TABLE boards ADD COLUMN clarification_status TEXT",
        "ALTER TABLE boards ADD COLUMN clarification_questions TEXT",
        "ALTER TABLE boards ADD COLUMN clarification_answers TEXT",
        "ALTER TABLE boards ADD COLUMN automation_agent_prompt TEXT",
        "ALTER TABLE boards ADD COLUMN automation_allowed_tools TEXT",
        "ALTER TABLE boards ADD COLUMN automation_tool_dir TEXT",
        "ALTER TABLE boards ADD COLUMN clarification_deadline TEXT",
        "ALTER TABLE boards ADD COLUMN clarification_attempt INTEGER",
        # Card 신규 컬럼
        "ALTER TABLE cards ADD COLUMN card_kind TEXT DEFAULT 'task'",
        # 의존성 기반 실행: 같은 run 내 task 인덱스 배열 (JSON), NULL이면 순차 폴백
        "ALTER TABLE cards ADD COLUMN depends_on TEXT",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass  # column already exists


def _migrate_legacy_cards(conn):
    """run_id 없는 기존 카드들에 대해 board별 첫 번째 run을 생성해 연결"""
    orphan_board_ids = conn.execute(
        "SELECT DISTINCT board_id FROM cards WHERE run_id IS NULL AND board_id IS NOT NULL"
    ).fetchall()

    for (bid,) in orphan_board_ids:
        # 이 보드에 이미 run이 있는지 확인
        existing_run = conn.execute(
            "SELECT id FROM runs WHERE board_id=? ORDER BY id LIMIT 1", (bid,)
        ).fetchone()

        if existing_run:
            run_id = existing_run[0]
        else:
            # Run #1 생성 (기존 보드 상태 반영)
            board = conn.execute("SELECT status, session_id FROM boards WHERE id=?", (bid,)).fetchone()
            status = board[0] if board else "done"
            session_id = board[1] if board else None
            cur = conn.execute(
                "INSERT INTO runs (board_id, status, session_id, trigger) VALUES (?,?,?,'manual')",
                (bid, status or "done", session_id),
            )
            run_id = cur.lastrowid

        conn.execute("UPDATE cards SET run_id=? WHERE board_id=? AND run_id IS NULL", (run_id, bid))


# ── Boards ───────────────────────────────────────────────────────────────────

def create_board(name: str, description: str = "", cron_expr: str = None,
                 approval_mode: str = "auto", project_path: str = None,
                 status: str = "generating") -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO boards (name, description, cron_expr, approval_mode, project_path, status) VALUES (?,?,?,?,?,?)",
            (name, description, cron_expr, approval_mode, project_path, status),
        )
        return cur.lastrowid


def update_board_status(board_id: int, status: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE boards SET status=? WHERE id=?", (status, board_id))


def update_board_approval_mode(board_id: int, mode: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE boards SET approval_mode=? WHERE id=?", (mode, board_id))


def update_board_project_path(board_id: int, project_path):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE boards SET project_path=? WHERE id=?", (project_path, board_id))


def update_board_cron(board_id: int, cron_expr):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE boards SET cron_expr=? WHERE id=?", (cron_expr, board_id))


def update_board_github(board_id: int, github_repo: str, github_installation_id: int, github_ref: str = "main"):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE boards SET source_type='github', github_repo=?, github_installation_id=?, github_ref=? WHERE id=?",
            (github_repo, github_installation_id, github_ref, board_id),
        )


def save_board_workspace(board_id: int, workspace_path: str, sha: str = None):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE boards SET workspace_path=?, github_last_sha=? WHERE id=?",
            (workspace_path, sha, board_id),
        )


def get_boards():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM boards ORDER BY id DESC")]


def get_boards_by_project_path(project_path: str) -> list:
    """같은 project_path를 가진 활성 보드 목록 반환 (충돌 가드용)."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, name FROM boards WHERE project_path=? AND status != 'deleted' ORDER BY id DESC",
            (str(project_path),),
        ).fetchall()
        return [dict(r) for r in rows]


def get_board(board_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM boards WHERE id=?", (board_id,)).fetchone()
        return dict(row) if row else None


def delete_board(board_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        run_ids = [r[0] for r in conn.execute("SELECT id FROM runs WHERE board_id=?", (board_id,))]
        for rid in run_ids:
            card_ids = [c[0] for c in conn.execute("SELECT id FROM cards WHERE run_id=?", (rid,))]
            for cid in card_ids:
                conn.execute("DELETE FROM feedback WHERE card_id=?", (cid,))
            conn.execute("DELETE FROM cards WHERE run_id=?", (rid,))
        conn.execute("DELETE FROM runs WHERE board_id=?", (board_id,))
        conn.execute("DELETE FROM agents WHERE board_id=?", (board_id,))
        conn.execute("DELETE FROM boards WHERE id=?", (board_id,))


# ── Runs ─────────────────────────────────────────────────────────────────────

def create_run(board_id: int, trigger: str = "manual") -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO runs (board_id, trigger) VALUES (?,?)",
            (board_id, trigger),
        )
        return cur.lastrowid


def update_run_status(run_id: int, status: str):
    with sqlite3.connect(DB_PATH) as conn:
        finished = "datetime('now')" if status in ("done", "error") else "NULL"
        conn.execute(
            f"UPDATE runs SET status=?, finished_at={finished} WHERE id=?",
            (status, run_id),
        )


def save_run_session_id(run_id: int, session_id: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE runs SET session_id=? WHERE id=?", (session_id, run_id))


def get_run_session_id(run_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT session_id FROM runs WHERE id=?", (run_id,)).fetchone()
        return row[0] if row else None


def get_run(run_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return dict(row) if row else None


def get_runs(board_id: int, limit: int = 30):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(
            "SELECT * FROM runs WHERE board_id=? ORDER BY id DESC LIMIT ?",
            (board_id, limit),
        )]


def get_latest_run_id(board_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT id FROM runs WHERE board_id=? ORDER BY id DESC LIMIT 1", (board_id,)
        ).fetchone()
        return row[0] if row else None


def delete_run(run_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        card_ids = [c[0] for c in conn.execute("SELECT id FROM cards WHERE run_id=?", (run_id,))]
        for cid in card_ids:
            conn.execute("DELETE FROM feedback WHERE card_id=?", (cid,))
        conn.execute("DELETE FROM cards WHERE run_id=?", (run_id,))
        conn.execute("DELETE FROM runs WHERE id=?", (run_id,))


# ── Cards ────────────────────────────────────────────────────────────────────

def create_card(board_id: int, run_id: int, title: str,
                description: str = "", agent_role: str = "",
                design_system: str = None, depends_on: list = None) -> int:
    import json as _json
    depends_on_str = _json.dumps(depends_on) if depends_on is not None else None
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO cards (board_id, run_id, title, description, agent_role, design_system, depends_on) VALUES (?,?,?,?,?,?,?)",
            (board_id, run_id, title, description, agent_role, design_system, depends_on_str),
        )
        return cur.lastrowid


def get_cards(board_id: int):
    """Legacy: 보드의 최신 run 카드 반환"""
    run_id = get_latest_run_id(board_id)
    if run_id is None:
        return []
    return get_cards_for_run(run_id)


def get_cards_for_run(run_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM cards WHERE run_id=? ORDER BY id", (run_id,)
        )]
        # 카드별 미답변 agent_reply 수 집계
        pending = {r["card_id"]: r["cnt"] for r in conn.execute(
            """
            SELECT f.card_id, COUNT(*) as cnt
            FROM feedback f
            WHERE f.type = 'agent_reply'
              AND NOT EXISTS (
                SELECT 1 FROM feedback c WHERE c.parent_id = f.id
              )
            GROUP BY f.card_id
            """
        )}
        for row in rows:
            row["pending_replies"] = pending.get(row["id"], 0)
        return rows


def update_card_status(card_id: int, status: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE cards SET status=?, updated_at=datetime('now') WHERE id=?",
            (status, card_id),
        )


def append_card_output(card_id: int, chunk: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE cards SET output = COALESCE(output,'') || ? WHERE id=?",
            (chunk, card_id),
        )


def clear_card_output(card_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE cards SET output=NULL, status='backlog', updated_at=datetime('now') WHERE id=?",
            (card_id,),
        )


def get_card(card_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        return dict(row) if row else None


def save_card_session_id(card_id: int, session_id: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE cards SET session_id=? WHERE id=?", (session_id, card_id))


def get_card_session_id(card_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT session_id FROM cards WHERE id=?", (card_id,)).fetchone()
        return row[0] if row else None


def update_card_artifact(card_id: int, artifact_type: str, run_command: str,
                         artifact_port: int = None, artifact_cwd: str = None):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE cards SET artifact_type=?, run_command=?, artifact_port=?, artifact_cwd=? WHERE id=?",
            (artifact_type, run_command, artifact_port, artifact_cwd, card_id),
        )


def update_card_artifact_cwd(card_id: int, cwd: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE cards SET artifact_cwd=? WHERE id=?", (cwd, card_id))


# ── Agents ───────────────────────────────────────────────────────────────────

AGENT_COLORS = ["#6366f1", "#ec4899", "#f59e0b", "#10b981", "#3b82f6", "#8b5cf6", "#ef4444"]


def create_agent(board_id: int, name: str, role: str = "", idx: int = 0) -> int:
    color = AGENT_COLORS[idx % len(AGENT_COLORS)]
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO agents (board_id, name, role, color) VALUES (?,?,?,?)",
            (board_id, name, role, color),
        )
        return cur.lastrowid


def get_agents(board_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(
            "SELECT * FROM agents WHERE board_id=?", (board_id,)
        )]


def set_agent_status(board_id: int, agent_name: str, status: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE agents SET status=? WHERE board_id=? AND name=?",
            (status, board_id, agent_name),
        )


# ── Feedback ──────────────────────────────────────────────────────────────────

def add_feedback(card_id: int, ftype: str, content: str = "",
                 author: str = "user", parent_id: int = None) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO feedback (card_id, type, content, author, parent_id) VALUES (?,?,?,?,?)",
            (card_id, ftype, content, author, parent_id),
        )
        return cur.lastrowid


def get_feedback(card_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(
            "SELECT * FROM feedback WHERE card_id=? ORDER BY id", (card_id,)
        )]


# ── Settings ──────────────────────────────────────────────────────────────────

def get_setting(key: str):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else None


def set_setting(key: str, value: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


# ── Orchestration Engine Helpers ──────────────────────────────────────────────

def update_board_fields(board_id: int, fields: dict):
    """여러 필드를 한 번에 업데이트"""
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [board_id]
    with sqlite3.connect(DB_PATH) as c:
        c.execute(f"UPDATE boards SET {sets} WHERE id=?", vals)


def create_clarification_card(board_id: int, questions: list) -> int:
    """clarification 카드 생성"""
    import json
    run_id = get_latest_run_id(board_id)
    if not run_id:
        run_id = create_run(board_id, trigger="manual")

    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(
            "INSERT INTO cards (board_id, run_id, title, status, card_kind, output) VALUES (?,?,?,?,?,?)",
            (board_id, run_id, "추가 정보가 필요합니다", "awaiting_user", "clarification", json.dumps(questions, ensure_ascii=False))
        )
        return cur.lastrowid


def save_clarification_answers(board_id: int, answers: dict):
    """clarification 답변 저장"""
    import json
    with sqlite3.connect(DB_PATH) as c:
        c.execute(
            "UPDATE boards SET clarification_answers=?, clarification_status='resolved' WHERE id=?",
            (json.dumps(answers, ensure_ascii=False), board_id)
        )


def update_board_automation_spec(board_id: int, prompt: str, tools: list, tool_dir: str):
    """automation 스펙 저장"""
    import json
    with sqlite3.connect(DB_PATH) as c:
        c.execute(
            "UPDATE boards SET automation_agent_prompt=?, automation_allowed_tools=?, automation_tool_dir=? WHERE id=?",
            (prompt, json.dumps(tools), tool_dir, board_id)
        )


def create_env_input_card(board_id: int, env_vars: list) -> int:
    """환경 변수 입력 카드 생성"""
    import json
    run_id = get_latest_run_id(board_id)
    if not run_id:
        run_id = create_run(board_id, trigger="manual")

    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(
            "INSERT INTO cards (board_id, run_id, title, status, card_kind, output) VALUES (?,?,?,?,?,?)",
            (board_id, run_id, "환경 변수 설정이 필요합니다", "awaiting_user", "env_input", json.dumps(env_vars, ensure_ascii=False))
        )
        return cur.lastrowid


def create_runtime_guide_card(board_id: int, payload: dict, parent_card_id: int = None) -> int:
    """실패 진단 결과로 spawn된 런타임 가이드 카드 생성."""
    import json as _json
    from datetime import datetime
    payload = dict(payload)
    payload["parent_card_id"] = parent_card_id
    payload["created_at"] = datetime.utcnow().isoformat()
    run_id = get_latest_run_id(board_id)
    if not run_id:
        run_id = create_run(board_id, trigger="manual")
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(
            "INSERT INTO cards (board_id, run_id, title, status, card_kind, output) VALUES (?,?,?,?,?,?)",
            (board_id, run_id,
             payload.get("message", "설정이 필요합니다"),
             "awaiting_user", "runtime_guide",
             _json.dumps(payload, ensure_ascii=False))
        )
        return cur.lastrowid


def get_latest_run(board_id: int):
    """최신 run을 전체 데이터로 반환"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM runs WHERE board_id=? ORDER BY id DESC LIMIT 1", (board_id,)
        ).fetchone()
        return dict(row) if row else None


def get_run_cards(run_id: int):
    """run의 모든 카드 반환"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(
            "SELECT * FROM cards WHERE run_id=? ORDER BY id", (run_id,)
        )]


def update_card(card_id: int, **kwargs):
    """카드 필드 업데이트"""
    if not kwargs:
        return
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [card_id]
    with sqlite3.connect(DB_PATH) as c:
        c.execute(f"UPDATE cards SET {sets} WHERE id=?", vals)


def insert_card(board_id: int, title: str, status: str = "backlog", agent_role: str = None) -> int:
    """카드 생성 (run 없이)"""
    run_id = get_latest_run_id(board_id)
    if not run_id:
        run_id = create_run(board_id, trigger="manual")

    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(
            "INSERT INTO cards (board_id, run_id, title, status, agent_role) VALUES (?,?,?,?,?)",
            (board_id, run_id, title, status, agent_role)
        )
        return cur.lastrowid
