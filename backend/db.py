"""SQLite storage layer for DRISHTI.

Standard library only - no external dependencies.
"""

import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("DRISHTI_DATA_DIR") or os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "drishti.db")

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT UNIQUE NOT NULL,
    password     TEXT NOT NULL,
    full_name    TEXT NOT NULL,
    role         TEXT NOT NULL,          -- ministry | state | district | mp
    scope_state  TEXT,
    scope_district TEXT
);

CREATE TABLE IF NOT EXISTS works (
    work_id            TEXT PRIMARY KEY,
    work_name          TEXT NOT NULL,
    category           TEXT NOT NULL,
    mp_name            TEXT NOT NULL,
    house              TEXT NOT NULL,
    state              TEXT NOT NULL,
    district           TEXT NOT NULL,
    agency             TEXT NOT NULL,
    recommended_date   TEXT,
    sanction_date      TEXT,
    sanction_amount    REAL,
    estimate_amount    REAL,
    expenditure        REAL,
    physical_progress  REAL,
    expected_completion TEXT,
    actual_completion  TEXT,
    status             TEXT,
    beneficiaries      INTEGER,
    completeness       REAL,
    fiscal_year        TEXT
);

CREATE TABLE IF NOT EXISTS payments (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id   TEXT NOT NULL REFERENCES works(work_id),
    pay_date  TEXT NOT NULL,
    amount    REAL NOT NULL,
    progress_at_payment REAL,
    voucher   TEXT
);

CREATE TABLE IF NOT EXISTS progress_updates (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id   TEXT NOT NULL REFERENCES works(work_id),
    update_date TEXT NOT NULL,
    progress  REAL NOT NULL,
    remark    TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id       TEXT NOT NULL REFERENCES works(work_id),
    risk_score    REAL NOT NULL,
    severity      TEXT NOT NULL,          -- critical | high | medium | low
    reason_codes  TEXT NOT NULL,          -- JSON array
    evidence      TEXT NOT NULL,          -- JSON object
    confidence    REAL NOT NULL,
    status        TEXT NOT NULL DEFAULT 'open',   -- open | in_review | actioned | dismissed
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    due_at        TEXT,                   -- SLA deadline (severity based)
    assignee      TEXT                    -- username of the owning officer
);

CREATE TABLE IF NOT EXISTS alert_actions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id   INTEGER NOT NULL REFERENCES alerts(id),
    username   TEXT NOT NULL,
    action     TEXT NOT NULL,
    note       TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id   INTEGER NOT NULL REFERENCES alerts(id),
    username   TEXT NOT NULL,
    useful     INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    username   TEXT NOT NULL,
    action     TEXT NOT NULL,
    entity     TEXT,
    detail     TEXT
);

CREATE TABLE IF NOT EXISTS comments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id    TEXT NOT NULL,
    username   TEXT NOT NULL,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist (
    username   TEXT NOT NULL,
    work_id    TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (username, work_id)
);

CREATE TABLE IF NOT EXISTS saved_views (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT NOT NULL,
    name       TEXT NOT NULL,
    filters    TEXT NOT NULL,
    shared     INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT NOT NULL,
    kind       TEXT NOT NULL,
    title      TEXT NOT NULL,
    body       TEXT,
    work_id    TEXT,
    created_at TEXT NOT NULL,
    read_at    TEXT
);

CREATE TABLE IF NOT EXISTS policy_versions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT NOT NULL,
    note       TEXT,
    policy     TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_comments_work ON comments(work_id);
CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(username, read_at);
CREATE INDEX IF NOT EXISTS idx_alerts_work ON alerts(work_id);
CREATE INDEX IF NOT EXISTS idx_payments_work ON payments(work_id);
CREATE INDEX IF NOT EXISTS idx_progress_work ON progress_updates(work_id);
CREATE INDEX IF NOT EXISTS idx_works_district ON works(state, district);
"""


def connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn):
    conn.executescript(SCHEMA)
    # lightweight migrations for databases created by earlier versions
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(alerts)").fetchall()}
    for name in ("due_at", "assignee"):
        if name not in cols:
            conn.execute(f"ALTER TABLE alerts ADD COLUMN {name} TEXT")
    conn.commit()


def is_seeded(conn):
    try:
        row = conn.execute("SELECT COUNT(*) AS c FROM works").fetchone()
        return bool(row and row["c"] > 0)
    except sqlite3.Error:
        return False


def log_audit(conn, username, action, entity=None, detail=None):
    from datetime import datetime, timezone

    conn.execute(
        "INSERT INTO audit_log (ts, username, action, entity, detail) VALUES (?,?,?,?,?)",
        (
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            username,
            action,
            entity,
            detail,
        ),
    )
    conn.commit()
