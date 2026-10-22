import sqlite3
import hashlib
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "explanations.db"


def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS explanation_cache (
            cache_key TEXT PRIMARY KEY,
            response_json TEXT NOT NULL
        )
    """)
    return conn


def _build_key(*parts: str) -> str:
    """
    Builds a deterministic cache key from one or more input strings.
    Lowercasing + hashing means "Casein" and "casein" hit the same cache entry.
    """
    raw = "|".join(p.strip().lower() for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_cached(*key_parts: str) -> dict | None:
    """Returns the cached response dict if present, else None."""
    key = _build_key(*key_parts)
    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT response_json FROM explanation_cache WHERE cache_key = ?", (key,)
        ).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def set_cached(response_dict: dict, *key_parts: str) -> None:
    """Stores a response dict in the cache, keyed by the given input parts."""
    key = _build_key(*key_parts)
    conn = _get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO explanation_cache (cache_key, response_json) VALUES (?, ?)",
            (key, json.dumps(response_dict)),
        )
        conn.commit()
    finally:
        conn.close()