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
    features_json TEXT    NOT NULL DEFAULT '{}',
    safety_flag   INTEGER NOT NULL DEFAULT 0, -- crisis language detected
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
"""


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(_SCHEMA)


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
) -> None:
    """Insert or replace the entry for a given (user, date)."""
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO entries
                (user_id, date, journal_text, sleep_hours, social_count,
                 energy, features_json, safety_flag, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET
                journal_text  = excluded.journal_text,
                sleep_hours   = excluded.sleep_hours,
                social_count  = excluded.social_count,
                energy        = excluded.energy,
                features_json = excluded.features_json,
                safety_flag   = excluded.safety_flag,
                created_at    = excluded.created_at
            """,
            (
                user_id,
                date,
                journal_text,
                sleep_hours,
                social_count,
                energy,
                json.dumps(features),
                1 if safety_flag else 0,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


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


def delete_all(user_id: str) -> int:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM entries WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM assessments WHERE user_id = ?", (user_id,))
        return cur.rowcount
