"""Session workspaces: all a session produces lives in one folder, deleted at the end (ADR 0003).

A session is one upload or one `di run`. In ephemeral mode (the default) the workspace is removed when the
session closes, also when the run fails; folders left behind by a crash are swept when the next session
starts, once their heartbeat is older than `ORPHAN_AFTER_S`.
"""

from __future__ import annotations

import shutil
import time
import uuid
from pathlib import Path
from types import TracebackType

from drawing_intelligence.settings import Settings
from drawing_intelligence.storage.cache import ResponseCache
from drawing_intelligence.storage.telemetry import Telemetry

HEARTBEAT = ".heartbeat"
ORPHAN_AFTER_S = 12 * 3600


def sweep_orphans(sessions_dir: Path, older_than_s: float = ORPHAN_AFTER_S) -> list[str]:
    """Delete session folders whose heartbeat is older than `older_than_s`. Returns the removed ids."""
    removed = []
    if not sessions_dir.exists():
        return removed
    now = time.time()
    for folder in sessions_dir.iterdir():
        if not folder.is_dir():
            continue
        beat = folder / HEARTBEAT
        last = beat.stat().st_mtime if beat.exists() else folder.stat().st_mtime
        if now - last > older_than_s:
            shutil.rmtree(folder, ignore_errors=True)
            removed.append(folder.name)
    return removed


class Session:
    def __init__(self, settings: Settings, session_id: str | None = None):
        self.settings = settings
        self.id = session_id or uuid.uuid4().hex[:12]
        self.workspace = settings.sessions_dir / self.id
        self.telemetry = Telemetry(settings.telemetry_db)
        self.status = "running"
        self.n_pages: int | None = None
        self._closed = False

    @property
    def ephemeral(self) -> bool:
        return self.settings.retention == "ephemeral"

    @property
    def checkpoint_db(self) -> Path:
        return self.workspace / "session.db"

    @property
    def cache(self) -> ResponseCache:
        return ResponseCache(self.workspace / "cache" if self.ephemeral else self.settings.cache_dir)

    def heartbeat(self) -> None:
        (self.workspace / HEARTBEAT).touch()

    def open(self) -> Session:
        if self.ephemeral:
            sweep_orphans(self.settings.sessions_dir)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.heartbeat()
        self.telemetry.start_session(self.id, self.settings.retention)
        return self

    def close(self, status: str | None = None) -> None:
        if self._closed:
            return
        self._closed = True
        self.telemetry.end_session(self.id, status or self.status, self.n_pages)
        if self.ephemeral:
            shutil.rmtree(self.workspace, ignore_errors=True)

    def __enter__(self) -> Session:
        return self.open()

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self.close("error" if exc_type else None)
