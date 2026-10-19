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

        # ---- accounts ----
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                allergens_json TEXT NOT NULL,
                prefs_json TEXT NOT NULL DEFAULT '{}'
            )
        """)
        # scans become per-user; old rows keep user_id NULL and are never shown
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(scans)").fetchall()]
        if "user_id" not in cols:
            conn.execute("ALTER TABLE scans ADD COLUMN user_id INTEGER")
        conn.commit()
    finally:
        conn.close()


def create_user(email: str, password_hash: str) -> dict:
    conn = _get_connection()
    try:
        cur = conn.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", (email, password_hash))
        user_id = cur.lastrowid
        conn.execute("INSERT INTO user_profiles (user_id, allergens_json) VALUES (?, '[]')", (user_id,))
        conn.commit()
        return {"id": user_id, "email": email}
    finally:
        conn.close()


def get_user_by_email(email: str) -> Optional[dict]:
    conn = _get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_session(token_hash: str, user_id: int, days: int = 30) -> None:
    conn = _get_connection()
    try:
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, datetime('now', ?))",
            (token_hash, user_id, f"+{days} days"),
        )
        conn.commit()
    finally:
        conn.close()


def get_user_by_token_hash(token_hash: str) -> Optional[dict]:
    conn = _get_connection()
    try:
        row = conn.execute(
            """SELECT u.id, u.email FROM sessions s JOIN users u ON u.id = s.user_id
               WHERE s.token_hash = ? AND s.expires_at > datetime('now')""",
            (token_hash,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_session(token_hash: str) -> None:
    conn = _get_connection()
    try:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
        conn.commit()
    finally:
        conn.close()


def save_scan(scan: dict, user_id: int) -> None:
    conn = _get_connection()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO scans
               (scan_id, product_name, date, verdict, flagged_ingredients_json, note, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (scan["scanId"], scan["productName"], scan["date"], scan["verdict"],
             json.dumps(scan["flaggedIngredients"]), scan.get("note"), user_id),
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


def get_scan(scan_id: str, user_id: int) -> Optional[dict]:
    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM scans WHERE scan_id = ? AND user_id = ?", (scan_id, user_id)
        ).fetchone()
        return _row_to_scan(row) if row else None
    finally:
        conn.close()


def list_scans(user_id: int) -> List[dict]:
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM scans WHERE user_id = ? ORDER BY created_at DESC, rowid DESC", (user_id,)
        ).fetchall()
        return [_row_to_scan(r) for r in rows]
    finally:
        conn.close()


def get_profile(user_id: int) -> dict:
    conn = _get_connection()
    try:
        row = conn.execute("SELECT allergens_json FROM user_profiles WHERE user_id = ?", (user_id,)).fetchone()
        return {"allergens": json.loads(row["allergens_json"]) if row else []}
    finally:
        conn.close()


def set_profile(user_id: int, allergens: List[str]) -> dict:
    conn = _get_connection()
    try:
        conn.execute(
            "INSERT INTO user_profiles (user_id, allergens_json) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET allergens_json = excluded.allergens_json",
            (user_id, json.dumps(allergens)),
        )
        conn.commit()
        return {"allergens": allergens}
    finally:
        conn.close()


def get_prefs(user_id: int) -> dict:
    conn = _get_connection()
    try:
        row = conn.execute("SELECT prefs_json FROM user_profiles WHERE user_id = ?", (user_id,)).fetchone()
        return json.loads(row["prefs_json"]) if row else {}
    finally:
        conn.close()


def set_prefs(user_id: int, prefs: dict) -> None:
    conn = _get_connection()
    try:
        conn.execute(
            "INSERT INTO user_profiles (user_id, allergens_json, prefs_json) VALUES (?, '[]', ?) "
            "ON CONFLICT(user_id) DO UPDATE SET prefs_json = excluded.prefs_json",
            (user_id, json.dumps(prefs)),
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