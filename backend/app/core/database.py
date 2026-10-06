"""
SafeBite persistence — SQLite
==============================
Replaces the old in-memory SCANS_DB / USER_PROFILE dicts in main.py.
Same idea as app/cache/explanation_cache.py (raw sqlite3, no ORM) so the
codebase doesn't need a new dependency for this.

Why this matters: with in-memory dicts, every `uvicorn --reload` or crash
wiped all scan history and the user's allergen profile. That's fine for a
30-second demo, not fine for anything you show live more than once, or for
grading where a reviewer might restart the server between sections.

Nothing above the functions in this file needs to know it's SQLite —
main.py just calls save_scan / get_scan / list_scans / get_profile /
set_profile, same shape as before.
"""

import json
import os
import sqlite3
from pathlib import Path
from typing import List, Optional

# Overridable via env var so tests (see tests/conftest.py) can point this
# at a throwaway file instead of the real dev database — otherwise every
# test run would leave scan rows behind in the database you actually use
# while developing.
DB_PATH = Path(os.getenv("SAFEBITE_DB_PATH", str(Path(__file__).parent / "safebite.db")))


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Creates tables if they don't exist yet. Safe to call on every startup."""
    conn = _get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                scan_id TEXT PRIMARY KEY,
                product_name TEXT NOT NULL,
                date TEXT NOT NULL,
                verdict TEXT NOT NULL,
                flagged_ingredients_json TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                allergens_json TEXT NOT NULL
            )
        """)
        # Single-row profile table; make sure the row exists.
        conn.execute("""
            INSERT OR IGNORE INTO profile (id, allergens_json) VALUES (1, '[]')
        """)
        conn.commit()
    finally:
        conn.close()


def seed_demo_scans_if_empty() -> None:
    """
    Seeds a few demo scans on first run only (table empty), so a fresh
    database isn't a blank dashboard and old links like
    verdict.html?scanId=s1 resolve. Never overwrites real data on restart.
    """
    conn = _get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
        if count > 0:
            return
        demo = [
            ("s1", "Classic Trail Mix", "3 days ago", "flagged",
             json.dumps([{"id": "peanut", "name": "Peanut"}]), None),
            ("s2", "Sparkling Lemon Soda", "2 days ago", "safe", json.dumps([]), None),
            ("s3", "Vanilla Wafer Cookies", "yesterday", "unclear", json.dumps([]), None),
        ]
        conn.executemany(
            """INSERT INTO scans (scan_id, product_name, date, verdict, flagged_ingredients_json, note)
               VALUES (?, ?, ?, ?, ?, ?)""",
            demo,
        )
        conn.commit()
    finally:
        conn.close()


def save_scan(scan: dict) -> None:
    conn = _get_connection()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO scans
               (scan_id, product_name, date, verdict, flagged_ingredients_json, note)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                scan["scanId"],
                scan["productName"],
                scan["date"],
                scan["verdict"],
                json.dumps(scan["flaggedIngredients"]),
                scan.get("note"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _row_to_scan(row: sqlite3.Row) -> dict:
    return {
        "scanId": row["scan_id"],
        "productName": row["product_name"],
        "date": row["date"],
        "verdict": row["verdict"],
        "flaggedIngredients": json.loads(row["flagged_ingredients_json"]),
        "note": row["note"],
    }


def get_scan(scan_id: str) -> Optional[dict]:
    conn = _get_connection()
    try:
        row = conn.execute("SELECT * FROM scans WHERE scan_id = ?", (scan_id,)).fetchone()
        return _row_to_scan(row) if row else None
    finally:
        conn.close()


def list_scans() -> List[dict]:
    conn = _get_connection()
    try:
        rows = conn.execute("SELECT * FROM scans ORDER BY created_at DESC").fetchall()
        return [_row_to_scan(r) for r in rows]
    finally:
        conn.close()


def get_profile() -> dict:
    conn = _get_connection()
    try:
        row = conn.execute("SELECT allergens_json FROM profile WHERE id = 1").fetchone()
        allergens = json.loads(row["allergens_json"]) if row else []
        return {"allergens": allergens}
    finally:
        conn.close()


def set_profile(allergens: List[str]) -> dict:
    conn = _get_connection()
    try:
        conn.execute(
            "UPDATE profile SET allergens_json = ? WHERE id = 1",
            (json.dumps(allergens),),
        )
        conn.commit()
        return {"allergens": allergens}
    finally:
        conn.close()