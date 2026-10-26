"""Check functions for `code` and `lookup` rules, one module per category (ADR 0010).

Importing this package registers every check. `registered()` is the registry the runner and `di rules` use.
"""

from __future__ import annotations

from pydantic import BaseModel

from drawing_intelligence.review.checks import (  # noqa: F401 - importing registers the checks
    consistency,
    fits,
    gdt,
    material,
    notes,
    surface_treatment,
    threads,
    title_block,
    tolerance,
)
from drawing_intelligence.review.checks._registry import (
    REGISTRY,
    CheckSpec,
    NoParams,
    NotApplicable,
    NotCheckable,
    check,
)


def registered() -> dict[str, CheckSpec]:
    return dict(REGISTRY)


def param_models() -> dict[str, type[BaseModel]]:
    """Check name -> params model, the shape `load_rulebook(checks=...)` validates against."""
    return {name: spec.params for name, spec in REGISTRY.items()}


__all__ = ["CheckSpec", "NoParams", "NotApplicable", "NotCheckable", "check", "param_models", "registered"]
