"""Runtime settings, read from environment variables and the repo's `.env` file.

API keys are held as `SecretStr` so they never appear in logs, reprs or error messages.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _project_root() -> Path:
    # src/drawing_intelligence/settings.py -> repo root. Falls back to the working directory when the
    # package is installed somewhere without a repo around it.
    root = Path(__file__).resolve().parents[2]
    return root if (root / "pyproject.toml").exists() else Path.cwd()


PROJECT_ROOT = _project_root()

Retention = Literal["ephemeral", "keep"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_prefix="DI_", extra="ignore", env_file_encoding="utf-8"
    )

    data_dir: Path = Path("data")
    sessions_root: Path | None = (
        None  # where session workspaces go; default data/sessions (the eval uses a temp dir)
    )
    config_dir: Path = Path("config")
    retention: Retention = "ephemeral"
    api_timeout_s: float = 600.0

    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    qwen_api_key: SecretStr | None = Field(default=None, validation_alias="QWEN_API_KEY")

    def _abs(self, p: Path) -> Path:
        return p if p.is_absolute() else PROJECT_ROOT / p

    @property
    def data_path(self) -> Path:
        return self._abs(self.data_dir)

    @property
    def config_path(self) -> Path:
        return self._abs(self.config_dir)

    @property
    def raw_dir(self) -> Path:
        return self.data_path / "raw"

    @property
    def sessions_dir(self) -> Path:
        return self._abs(self.sessions_root) if self.sessions_root else self.data_path / "sessions"

    @property
    def cache_dir(self) -> Path:
        return self.data_path / "cache"

    @property
    def baseline_dir(self) -> Path:
        return self.data_path / "baseline"

    @property
    def labels_dir(self) -> Path:
        return self.data_path / "labels"

    @property
    def telemetry_db(self) -> Path:
        return self.data_path / "telemetry.db"

    def api_key(self, env_name: str) -> str | None:
        """The key for a provider, looked up by the env-var name the model registry gives."""
        secret = {"OPENAI_API_KEY": self.openai_api_key, "QWEN_API_KEY": self.qwen_api_key}.get(env_name)
        return secret.get_secret_value() if secret else None


@lru_cache
def get_settings() -> Settings:
    return Settings()
