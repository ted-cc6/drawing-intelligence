"""The model registry (`config/models.yaml`, ADR 0004): which models exist, their cost, how to call them."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, model_validator

from drawing_intelligence.settings import get_settings

Role = Literal["understand", "review", "qa"]
PRICE_STALE_AFTER_DAYS = 60


class ProviderSpec(BaseModel):
    label: str
    api_key_env: str
    base_url: str | None = None
    max_tokens_param: Literal["max_tokens", "max_completion_tokens"]
    image_detail: str | None = None
    request: dict[str, Any] = {}


class Price(BaseModel):
    input_per_mtok: float
    output_per_mtok: float
    verified_on: date
    source: str

    def age_days(self, today: date | None = None) -> int:
        return ((today or date.today()) - self.verified_on).days


class Capabilities(BaseModel):
    vision: bool
    strict_json_schema: bool


class Thinking(BaseModel):
    default: str
    options: dict[str, dict[str, Any]]

    @model_validator(mode="after")
    def _default_is_an_option(self) -> Thinking:
        if self.default not in self.options:
            raise ValueError(f"thinking default {self.default!r} is not one of {list(self.options)}")
        return self


class ModelSpec(BaseModel):
    name: str = ""
    provider: str
    label: str
    roles: list[Role]
    capabilities: Capabilities
    max_output_tokens: int
    temperature: float | None = None
    request: dict[str, Any] = {}
    price: Price
    thinking: Thinking

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens / 1e6 * self.price.input_per_mtok + output_tokens / 1e6 * self.price.output_per_mtok
        )

    def thinking_level(self, level: str | None) -> str:
        level = level or self.thinking.default
        if level not in self.thinking.options:
            raise ValueError(
                f"{self.name} has no thinking option {level!r}; choose one of {list(self.thinking.options)}"
            )
        return level


class Registry(BaseModel):
    providers: dict[str, ProviderSpec]
    models: dict[str, ModelSpec]
    defaults: dict[Role, str]

    @model_validator(mode="after")
    def _consistent(self) -> Registry:
        for name, m in self.models.items():
            m.name = name
            if m.provider not in self.providers:
                raise ValueError(f"model {name}: unknown provider {m.provider!r}")
        for role, name in self.defaults.items():
            if name not in self.models:
                raise ValueError(f"default for {role}: unknown model {name!r}")
            if role not in self.models[name].roles:
                raise ValueError(f"default for {role}: model {name} is not allowed for that role")
        return self

    def model(self, name: str | None, role: Role) -> ModelSpec:
        """The model to use for a role: the named one (validated), or the role's default."""
        name = name or self.defaults[role]
        if name not in self.models:
            raise ValueError(f"unknown model {name!r}; registered: {list(self.models)}")
        spec = self.models[name]
        if role not in spec.roles:
            raise ValueError(f"model {name} is not allowed for role {role!r} (allowed: {spec.roles})")
        return spec

    def provider(self, spec: ModelSpec) -> ProviderSpec:
        return self.providers[spec.provider]


def load_registry(path: Path | None = None) -> Registry:
    path = path or get_settings().config_path / "models.yaml"
    return Registry.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
