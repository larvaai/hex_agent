"""SQLite checkpoint for the TaskLoop Blackboard — the truth for resume. Epic E10 S10.10.

One SQLite db per run holds the latest serialized TaskLoopState. The loop saves
after every worker turn (and at each node boundary), so a run interrupted mid-round
can resume from the persisted Blackboard without re-running a completed turn.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from observability.event_log import runs_dir
from supervisor.state import TaskLoopState, decode_taskloop_state, encode_taskloop_state


def taskloop_db_path(run_id: str) -> Path:
    return runs_dir() / run_id / "taskloop.sqlite"


class SqliteTaskLoopStore:
    def __init__(self, run_id: str, *, path: Path | None = None) -> None:
        self.run_id = run_id
        self.path = path or taskloop_db_path(run_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS taskloop (run_id TEXT PRIMARY KEY, state TEXT NOT NULL)")

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.path))

    def save(self, state: TaskLoopState) -> None:
        blob = json.dumps(encode_taskloop_state(state))
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO taskloop(run_id, state) VALUES(?, ?) "
                "ON CONFLICT(run_id) DO UPDATE SET state=excluded.state",
                (self.run_id, blob),
            )

    def load(self) -> TaskLoopState | None:
        with self._conn() as conn:
            row = conn.execute("SELECT state FROM taskloop WHERE run_id=?", (self.run_id,)).fetchone()
        return decode_taskloop_state(json.loads(row[0])) if row else None
