"""The check registry: rulebook `check` names -> the function that runs them and its params model."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict

from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.rulebook import Rule
from drawing_intelligence.schemas import Finding

CheckFn = Callable[[ReviewContext, Rule, Any], list[Finding]]


class NoParams(BaseModel):
    """For checks that take no params: any param in the rule is a mistake."""

    model_config = ConfigDict(extra="forbid")


class NotApplicable(Exception):
    """The rule does not apply to this drawing (e.g. no threads on it)."""


class NotCheckable(Exception):
    """The rule applies but this drawing lacks what the check needs (e.g. no title-block fields)."""


@dataclass(frozen=True)
class CheckSpec:
    name: str
    fn: CheckFn
    params: type[BaseModel]


REGISTRY: dict[str, CheckSpec] = {}


def check(name: str, params: type[BaseModel] = NoParams) -> Callable[[CheckFn], CheckFn]:
    """Register a check function under its rulebook name.

    A check is pure: `fn(ctx, rule, params) -> list[Finding]`, findings made with `new_finding(rule, ...)`,
    an empty list for a pass, `NotApplicable` / `NotCheckable` for the other outcomes. No I/O, no LLM.
    """

    def register(fn: CheckFn) -> CheckFn:
        if name in REGISTRY:
            raise ValueError(f"check {name!r} is registered twice")
        REGISTRY[name] = CheckSpec(name, fn, params)
        return fn

    return register
