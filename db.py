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
        """)

        # 기존 DB 마이그레이션 (컬럼 누락 시 추가)
        _migrate(conn)

        # 기존 cards에 run_id 없는 경우: board별 Run #1 자동 생성
        _migrate_legacy_cards(conn)


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


def get_boards():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM boards ORDER BY id DESC")]


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
                description: str = "", agent_role: str = "") -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO cards (board_id, run_id, title, description, agent_role) VALUES (?,?,?,?,?)",
            (board_id, run_id, title, description, agent_role),
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
        return [dict(r) for r in conn.execute(
            "SELECT * FROM cards WHERE run_id=? ORDER BY id", (run_id,)
        )]


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
