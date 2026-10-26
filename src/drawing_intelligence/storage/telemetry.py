"""Persistent, content-free telemetry: one row per session and one per LLM call (ADR 0003).

Never store drawing content here: no file names, drawing numbers, prompts, replies or extracted text.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    retention    TEXT NOT NULL,
    status       TEXT NOT NULL,
    n_pages      INTEGER
);
CREATE TABLE IF NOT EXISTS llm_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL,
    node            TEXT NOT NULL,
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    thinking        TEXT NOT NULL,
    input_tokens    INTEGER NOT NULL,
    output_tokens   INTEGER NOT NULL,
    reasoning_tokens INTEGER NOT NULL,
    cost_usd        REAL NOT NULL,      -- money actually spent: 0 for a cache hit
    latency_s       REAL NOT NULL,
    cached          INTEGER NOT NULL,
    status          TEXT NOT NULL,      -- ok | error
    error_type      TEXT,               -- exception class only, never the message (it may echo content)
    created_at      TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class CallRecord:
    session_id: str
    node: str
    provider: str
    model: str
    thinking: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cost_usd: float
    latency_s: float
    cached: bool
    status: str
    error_type: str | None = None


class Telemetry:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def start_session(self, session_id: str, retention: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO sessions (session_id, started_at, retention, status) "
                "VALUES (?, ?, ?, 'running') "  # a kept session reopened (di ask --session) runs again
                "ON CONFLICT(session_id) DO UPDATE SET status = 'running', ended_at = NULL",
                (session_id, _now(), retention),
            )

    def end_session(self, session_id: str, status: str, n_pages: int | None = None) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE sessions SET ended_at = ?, status = ?, n_pages = COALESCE(?, n_pages) "
                "WHERE session_id = ?",
                (_now(), status, n_pages, session_id),
            )

    def record_call(self, rec: CallRecord) -> None:
        row = asdict(rec) | {"cached": int(rec.cached), "created_at": _now()}
        cols = ", ".join(row)
        with self._conn() as c:
            c.execute(
                f"INSERT INTO llm_calls ({cols}) VALUES ({', '.join('?' * len(row))})", tuple(row.values())
            )

    def calls(self, session_id: str | None = None) -> list[dict[str, Any]]:
        query, args = "SELECT * FROM llm_calls", ()
        if session_id:
            query, args = query + " WHERE session_id = ?", (session_id,)
        with self._conn() as c:
            c.row_factory = sqlite3.Row
            return [dict(r) for r in c.execute(query + " ORDER BY id", args)]

    def model_summary(self) -> list[dict[str, Any]]:
        """Average cost and latency per model and thinking level (non-cached, successful calls)."""
        with self._conn() as c:
            c.row_factory = sqlite3.Row
            rows = c.execute(
                """SELECT model, thinking, node, COUNT(*) AS calls,
                          AVG(latency_s) AS avg_latency_s, AVG(cost_usd) AS avg_cost_usd,
                          AVG(input_tokens) AS avg_input_tokens, AVG(output_tokens) AS avg_output_tokens,
                          SUM(cost_usd) AS total_cost_usd
                   FROM llm_calls WHERE cached = 0 AND status = 'ok'
                   GROUP BY model, thinking, node ORDER BY model, thinking, node"""
            )
            return [dict(r) for r in rows]
