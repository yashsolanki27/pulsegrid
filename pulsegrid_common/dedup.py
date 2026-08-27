"""
pulsegrid_common/dedup.py
=========================
Generic SQLite-backed dedup state store.

Stores: dedup_key (arbitrary string) -> last_reported_at (UTC ISO-8601 string).

This is a generalisation of the reconciliation-job's original order_id-specific
DedupStore. The key is now a plain string so that any caller can namespace its
own dedup keys without coupling this module to a specific entity type.

Usage examples:
  reconciliation-job: key = f"order:{order_id}"
  api-health-monitor: key = f"endpoint:{method}:{url}"

Storage choice rationale:
  SQLite sidecar file (caller-supplied path).
  - No extra Postgres instance required for the caller.
  - Portable: runs anywhere Python runs; survives restarts.
  - Single-writer workload (non-concurrent jobs) -- SQLite is sufficient.
  - If migrated to a containerised environment, mount the file via a volume.
  See patterns.md, section "Dedup state storage".
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS dedup_state (
    dedup_key        TEXT PRIMARY KEY,
    last_reported_at TEXT NOT NULL
)
"""


class DedupStore:
    """Thread-unsafe but single-process safe SQLite dedup state.

    Parameters
    ----------
    db_path:
        File path to the SQLite database (created if absent).
    """

    def __init__(self, db_path: str) -> None:
        self._path = Path(db_path)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()

    def get_last_reported(self, dedup_key: str) -> "datetime | None":
        """Return last_reported_at (UTC-aware) for dedup_key, or None if never reported."""
        row = self._conn.execute(
            "SELECT last_reported_at FROM dedup_state WHERE dedup_key = ?",
            (dedup_key,),
        ).fetchone()
        if row is None:
            return None
        return datetime.fromisoformat(row[0]).replace(tzinfo=timezone.utc)

    def mark_reported(self, dedup_key: str, reported_at: datetime) -> None:
        """Upsert the last_reported_at for dedup_key."""
        ts = reported_at.astimezone(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO dedup_state (dedup_key, last_reported_at)
            VALUES (?, ?)
            ON CONFLICT(dedup_key) DO UPDATE SET last_reported_at = excluded.last_reported_at
            """,
            (dedup_key, ts),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
