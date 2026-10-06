from pathlib import Path

from drawing_intelligence.settings import PROJECT_ROOT, Settings


def test_defaults_are_safe(monkeypatch):
    monkeypatch.delenv("DI_RETENTION", raising=False)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.retention == "ephemeral"


def test_relative_paths_resolve_from_repo_root():
    s = Settings(_env_file=None, data_dir=Path("data"))  # type: ignore[call-arg]
    assert s.data_path == PROJECT_ROOT / "data"
    assert s.telemetry_db.parent == s.data_path


def test_keys_are_secret(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert "sk-test-123" not in repr(s)
    assert s.api_key("OPENAI_API_KEY") == "sk-test-123"
    assert s.api_key("UNKNOWN") is None
