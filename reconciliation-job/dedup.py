"""
reconciliation-job/dedup.py
===========================
Lightweight SQLite-backed dedup state store.

Stores: order_id -> last_reported_at (UTC ISO-8601 string).

Storage choice rationale:
  SQLite sidecar file (default: ./dedup_state.db).
  - No extra Postgres instance required for the job itself.
  - Portable: runs anywhere Python runs; survives restarts.
  - Single-writer workload (the job is not concurrent) -- SQLite is sufficient.
  - If migrated to a containerised environment, mount the file via a volume.
  See patterns.md, section "Dedup state storage".
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS dedup_state (
    order_id        INTEGER PRIMARY KEY,
    last_reported_at TEXT NOT NULL
)
"""


class DedupStore:
    """Thread-unsafe but single-process safe SQLite dedup state."""

    def __init__(self, db_path: str) -> None:
        self._path = Path(db_path)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()

    def get_last_reported(self, order_id: int) -> "datetime | None":
        """Return last_reported_at (UTC-aware) for order_id, or None if never reported."""
        row = self._conn.execute(
            "SELECT last_reported_at FROM dedup_state WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        if row is None:
            return None
        return datetime.fromisoformat(row[0]).replace(tzinfo=timezone.utc)

    def mark_reported(self, order_id: int, reported_at: datetime) -> None:
        """Upsert the last_reported_at for order_id."""
        ts = reported_at.astimezone(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO dedup_state (order_id, last_reported_at)
            VALUES (?, ?)
            ON CONFLICT(order_id) DO UPDATE SET last_reported_at = excluded.last_reported_at
            """,
            (order_id, ts),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
