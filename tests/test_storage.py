import os
import time

import pytest

from drawing_intelligence.storage import Session, Telemetry, sweep_orphans


def test_ephemeral_session_deletes_its_workspace(settings):
    with Session(settings) as s:
        (s.workspace / "extraction.json").write_text("{}", encoding="utf-8")
        assert s.workspace.exists()
    assert not s.workspace.exists()
    (row,) = [r for r in _sessions(settings) if r["session_id"] == s.id]
    assert row["status"] == "running" and row["ended_at"]  # closed normally without an explicit status


def test_workspace_deleted_even_when_the_run_fails(settings):
    with pytest.raises(RuntimeError), Session(settings) as s:
        raise RuntimeError("boom")
    assert not s.workspace.exists()
    assert next(r for r in _sessions(settings) if r["session_id"] == s.id)["status"] == "error"


def test_keep_mode_keeps_workspace_and_shares_cache(settings):
    settings.retention = "keep"
    with Session(settings) as s:
        pass
    assert s.workspace.exists()
    assert s.cache.folder == settings.cache_dir


def test_ephemeral_cache_lives_in_the_workspace(settings):
    s = Session(settings)
    assert s.cache.folder.is_relative_to(s.workspace)


def test_orphans_are_swept(settings):
    old = settings.sessions_dir / "crashed"
    old.mkdir(parents=True)
    (old / ".heartbeat").touch()
    past = time.time() - 13 * 3600
    os.utime(old / ".heartbeat", (past, past))
    fresh = settings.sessions_dir / "running"
    fresh.mkdir()
    (fresh / ".heartbeat").touch()
    assert sweep_orphans(settings.sessions_dir) == ["crashed"]
    assert fresh.exists() and not old.exists()


def _sessions(settings):
    tel = Telemetry(settings.telemetry_db)
    with tel._conn() as c:
        c.row_factory = __import__("sqlite3").Row
        return [dict(r) for r in c.execute("SELECT * FROM sessions")]
