import json
import sqlite3
from datetime import datetime, timezone
from typing import Any
from climateM1.core.config import CACHE_TTL_SECONDS, DATA_DIR, DATABASE_PATH

HISTORY_CACHE_VERSION = "v4"
SCENARIO_CACHE_VERSION = "v3"

def initialize_cache() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS climate_cache (
                cache_key TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                retrieved_at TEXT NOT NULL
            )
        """)


def get_cached(cache_key: str, allow_stale: bool = False) -> dict[str, Any] | None:
    initialize_cache()
    with sqlite3.connect(DATABASE_PATH) as connection:
        row = connection.execute(
            "SELECT payload, retrieved_at FROM climate_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if not row:
        return None
    retrieved_at = datetime.fromisoformat(row[1])
    age = (datetime.now(timezone.utc) - retrieved_at).total_seconds()
    if age > CACHE_TTL_SECONDS and not allow_stale:
        return None
    return json.loads(row[0])


def save_cached(cache_key: str, payload: dict[str, Any]) -> None:
    initialize_cache()
    retrieved_at = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            "INSERT INTO climate_cache(cache_key, payload, retrieved_at) VALUES (?, ?, ?) "
            "ON CONFLICT(cache_key) DO UPDATE SET payload=excluded.payload, retrieved_at=excluded.retrieved_at",
            (cache_key, json.dumps(payload), retrieved_at),
        )
