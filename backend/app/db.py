"""SQLite persistence layer.

Deliberately tiny and dependency-free (Python stdlib only). All behavioral
data lives in a single local file so the whole app is trivially self-hostable
and the user can delete everything with one call.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from .config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT    NOT NULL,
    date          TEXT    NOT NULL,          -- ISO date (YYYY-MM-DD)
    journal_text  TEXT    NOT NULL DEFAULT '',
    sleep_hours   REAL,
    social_count  INTEGER,
    energy        INTEGER,                    -- 1..5 self-report
    steps         INTEGER,                    -- passive: daily step count
    active_minutes INTEGER,                   -- passive: active/move minutes
    screen_time_min INTEGER,                  -- passive: phone screen time
    features_json TEXT    NOT NULL DEFAULT '{}',
    safety_flag   INTEGER NOT NULL DEFAULT 0, -- crisis language detected
    source        TEXT    NOT NULL DEFAULT 'user',
    created_at    TEXT    NOT NULL,
    UNIQUE(user_id, date)
);

CREATE TABLE IF NOT EXISTS assessments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT    NOT NULL,
    date          TEXT    NOT NULL,          -- ISO date (YYYY-MM-DD)
    instrument    TEXT    NOT NULL,          -- 'PHQ-9' | 'GAD-7'
    total         INTEGER NOT NULL,
    severity      TEXT    NOT NULL DEFAULT '',
    responses_json TEXT   NOT NULL DEFAULT '[]',
    created_at    TEXT    NOT NULL,
    UNIQUE(user_id, date, instrument)
);

CREATE TABLE IF NOT EXISTS contacts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT    NOT NULL,
    name          TEXT    NOT NULL,
    method        TEXT    NOT NULL DEFAULT 'other',
    detail        TEXT    NOT NULL DEFAULT '',
    notify_tier   INTEGER NOT NULL DEFAULT 3,
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS intervention_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT    NOT NULL,
    date          TEXT    NOT NULL,
    intervention_key TEXT NOT NULL,
    index_before  REAL,
    index_after   REAL,               -- null until resolved on next check-in
    delta         REAL,               -- index_after - index_before (negative = helped)
    created_at    TEXT    NOT NULL
);
"""

# Columns added after the initial release; ALTER TABLE for older DB files.
_MIGRATIONS = {
    "entries": {
        "steps": "INTEGER",
        "active_minutes": "INTEGER",
        "screen_time_min": "INTEGER",
        "source": "TEXT NOT NULL DEFAULT 'user'",
    },
}


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Add any columns missing from older database files."""
    for table, cols in _MIGRATIONS.items():
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, decl in cols.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(_SCHEMA)
        _migrate(conn)


def upsert_entry(
    *,
    user_id: str,
    date: str,
    journal_text: str,
    sleep_hours: float | None,
    social_count: int | None,
    energy: int | None,
    features: dict,
    safety_flag: bool,
    steps: int | None = None,
    active_minutes: int | None = None,
    screen_time_min: int | None = None,
    source: str = "user",
) -> None:
    """Insert or replace the entry for a given (user, date)."""
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO entries
                (user_id, date, journal_text, sleep_hours, social_count,
                 energy, steps, active_minutes, screen_time_min,
                 features_json, safety_flag, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET
                journal_text    = excluded.journal_text,
                sleep_hours     = excluded.sleep_hours,
                social_count    = excluded.social_count,
                energy          = excluded.energy,
                steps           = COALESCE(excluded.steps, entries.steps),
                active_minutes  = COALESCE(excluded.active_minutes, entries.active_minutes),
                screen_time_min = COALESCE(excluded.screen_time_min, entries.screen_time_min),
                features_json   = excluded.features_json,
                safety_flag     = excluded.safety_flag,
                source          = excluded.source,
                created_at      = excluded.created_at
            """,
            (
                user_id,
                date,
                journal_text,
                sleep_hours,
                social_count,
                energy,
                steps,
                active_minutes,
                screen_time_min,
                json.dumps(features),
                1 if safety_flag else 0,
                source,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def update_passive(
    *,
    user_id: str,
    date: str,
    steps: int | None = None,
    active_minutes: int | None = None,
    screen_time_min: int | None = None,
    sleep_hours: float | None = None,
) -> bool:
    """Update only passive fields on an existing entry. Returns True if a row
    was updated (i.e. an entry existed for that date)."""
    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE entries SET
                steps           = COALESCE(?, steps),
                active_minutes  = COALESCE(?, active_minutes),
                screen_time_min = COALESCE(?, screen_time_min),
                sleep_hours     = COALESCE(?, sleep_hours)
            WHERE user_id = ? AND date = ?
            """,
            (steps, active_minutes, screen_time_min, sleep_hours,
             user_id, date),
        )
        return cur.rowcount > 0


def get_entries(user_id: str) -> list[dict]:
    """Return all entries for a user ordered by date ascending."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM entries WHERE user_id = ? ORDER BY date ASC",
            (user_id,),
        ).fetchall()
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        d["features"] = json.loads(d.pop("features_json") or "{}")
        d["safety_flag"] = bool(d["safety_flag"])
        out.append(d)
    return out


def upsert_assessment(
    *,
    user_id: str,
    date: str,
    instrument: str,
    total: int,
    severity: str,
    responses: list[int] | None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO assessments
                (user_id, date, instrument, total, severity, responses_json,
                 created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date, instrument) DO UPDATE SET
                total          = excluded.total,
                severity       = excluded.severity,
                responses_json = excluded.responses_json,
                created_at     = excluded.created_at
            """,
            (
                user_id, date, instrument, int(total), severity,
                json.dumps(responses or []),
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def get_assessments(user_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM assessments WHERE user_id = ? ORDER BY date ASC",
            (user_id,),
        ).fetchall()
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        d["responses"] = json.loads(d.pop("responses_json") or "[]")
        out.append(d)
    return out


# --- Circle of Care contacts ------------------------------------------------
def add_contact(
    *, user_id: str, name: str, method: str, detail: str, notify_tier: int,
) -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO contacts
                (user_id, name, method, detail, notify_tier, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, name, method, detail, int(notify_tier),
             datetime.now(timezone.utc).isoformat()),
        )
        return {
            "id": cur.lastrowid, "name": name, "method": method,
            "detail": detail, "notify_tier": int(notify_tier),
        }


def get_contacts(user_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, method, detail, notify_tier FROM contacts "
            "WHERE user_id = ? ORDER BY id ASC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_contact(user_id: str, contact_id: int) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM contacts WHERE user_id = ? AND id = ?",
            (user_id, contact_id),
        )
        return cur.rowcount


# --- Intervention effectiveness log -----------------------------------------
def log_intervention(*, user_id: str, date: str, intervention_key: str,
                     index_before: float | None,
                     index_after: float | None = None) -> int:
    delta = None
    if index_before is not None and index_after is not None:
        delta = index_after - index_before
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO intervention_log
                (user_id, date, intervention_key, index_before, index_after,
                 delta, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, date, intervention_key, index_before, index_after, delta,
             datetime.now(timezone.utc).isoformat()),
        )
        return cur.lastrowid


def resolve_pending_interventions(user_id: str, index_after: float) -> int:
    """Fill in the outcome for any tried-but-unresolved interventions."""
    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE intervention_log
            SET index_after = ?, delta = ? - index_before
            WHERE user_id = ? AND index_after IS NULL AND index_before IS NOT NULL
            """,
            (index_after, index_after, user_id),
        )
        return cur.rowcount


def get_intervention_history(user_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT date, intervention_key, index_before, index_after, delta "
            "FROM intervention_log WHERE user_id = ? ORDER BY date ASC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_all(user_id: str) -> int:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM entries WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM assessments WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM contacts WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM intervention_log WHERE user_id = ?", (user_id,))
        return cur.rowcount
