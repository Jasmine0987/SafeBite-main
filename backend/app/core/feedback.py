"""
User feedback on verdicts ("it missed an allergen", "false alarm", ...).

Why it matters for the foundation: every reported miss is a hard test case.
Export these rows into the evaluation dataset (backend/eval) so accuracy is
measured on real failures, not only on the photos you collected up front.
"""
from __future__ import annotations

from typing import Optional

from app.core import database as db

KINDS = {"missed_allergen", "false_alarm", "unreadable", "wrong_product", "other"}


def init() -> None:
    conn = db._get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS verdict_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                scan_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                comment TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )""")
        conn.commit()
    finally:
        conn.close()


def save(user_id, scan_id: str, kind: str, comment: Optional[str]) -> None:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {sorted(KINDS)}")
    conn = db._get_connection()
    try:
        conn.execute(
            "INSERT INTO verdict_feedback (user_id, scan_id, kind, comment) VALUES (?, ?, ?, ?)",
            (str(user_id), scan_id, kind, (comment or "")[:1000]),
        )
        conn.commit()
    finally:
        conn.close()
