"""The rulebook: what to check on a drawing, as data in `config/rules/*.yaml`.

Each file holds a list of rules:

    rules:
      - id: TB-001
        category: title_block
        requirement: The title block states the material.
        severity: major
        check_type: lookup              # code | lookup | llm
        check: title_block_field        # the registered check function (code and lookup rules)
        params: {field: material, placeholder_ok: ["#"]}
        applies_to: {part_family: [prismatic, round], drawing_type: [machining]}
        source: {document: Check List.docx, section: Title block requirements}
        status: draft                   # draft | client_confirmed

`load_rulebook()` validates every file and reports *all* problems at once, so a drafted rulebook can be fixed
in one pass. With `checks` (check name -> params model), it also checks that each code/lookup rule names a
real check and that its params fit it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from drawing_intelligence.schemas.review import Category, EvidenceRef, Finding, Severity, Source
from drawing_intelligence.settings import get_settings

PartFamily = Literal["prismatic", "round"]
DrawingType = Literal["machining", "fabrication"]
RULE_ID_PATTERN = r"^[A-Z][A-Z0-9]*-\d{3}$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AppliesTo(_Strict):
    part_family: list[PartFamily] = ["prismatic", "round"]
    drawing_type: list[DrawingType] = ["machining", "fabrication"]


class RuleSource(_Strict):
    document: str = Field(description="e.g. Check List.docx, WP Specific Guidelines, IS 2102")
    section: str


class Rule(_Strict):
    id: str = Field(pattern=RULE_ID_PATTERN, description="category prefix + number, e.g. TB-001")
    category: Category
    requirement: str
    severity: Severity
    check_type: Source
    check: str | None = None
    params: dict[str, Any] = {}
    applies_to: AppliesTo = AppliesTo()
    source: RuleSource
    status: Literal["draft", "client_confirmed"] = "draft"

    @model_validator(mode="after")
    def _check_named(self) -> Rule:
        if self.check_type in ("code", "lookup") and not self.check:
            raise ValueError(f"a {self.check_type} rule must name its check function")
        return self

    @property
    def can_fail(self) -> bool:
        """LLM rules only ever raise warnings (Spike E)."""
        return self.check_type != "llm"

    def applies(self, part_family: PartFamily | None, drawing_type: DrawingType | None) -> bool:
        """Unknown family or type (None) means the rule applies: better a checked rule than a silent skip."""
        return (part_family is None or part_family in self.applies_to.part_family) and (
            drawing_type is None or drawing_type in self.applies_to.drawing_type
        )


class Rulebook(BaseModel):
    version: str = Field(description="hash of the rule files, recorded in every review result")
    rules: list[Rule] = []

    def get(self, rule_id: str) -> Rule:
        for r in self.rules:
            if r.id == rule_id:
                return r
        raise KeyError(f"no rule {rule_id!r} in the rulebook")

    def applicable(
        self, part_family: PartFamily | None = None, drawing_type: DrawingType | None = None
    ) -> list[Rule]:
        return [r for r in self.rules if r.applies(part_family, drawing_type)]


class RulebookError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__(
            f"{len(problems)} problem(s) in the rulebook:\n" + "\n".join(f"- {p}" for p in problems)
        )


def _version(files: list[Path]) -> str:
    h = hashlib.sha256()
    for f in files:
        h.update(f.name.encode("utf-8"))
        h.update(f.read_bytes().replace(b"\r\n", b"\n"))  # same version on Windows and Linux checkouts
    return h.hexdigest()[:12]


def load_rulebook(path: Path | None = None, checks: Mapping[str, type[BaseModel]] | None = None) -> Rulebook:
    """Load and validate every `*.yaml` in the rules folder. An empty or missing folder -> no rules."""
    folder = path or get_settings().config_path / "rules"
    files = sorted(folder.glob("*.yaml")) if folder.is_dir() else []
    rules: list[Rule] = []
    problems: list[str] = []
    seen: dict[str, str] = {}
    for f in files:
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            problems.append(f"{f.name}: not valid YAML ({e})")
            continue
        entries = data.get("rules") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            problems.append(f"{f.name}: expected a top-level `rules:` list")
            continue
        for i, entry in enumerate(entries, 1):
            label = f"{f.name} #{i}" + (
                f" ({entry.get('id')})" if isinstance(entry, dict) and entry.get("id") else ""
            )
            try:
                rule = Rule.model_validate(entry)
            except ValidationError as e:
                problems += [
                    f"{label}: {'.'.join(map(str, err['loc'])) or 'rule'}: {err['msg']}" for err in e.errors()
                ]
                continue
            if rule.id in seen:
                problems.append(f"{label}: duplicate id, already defined in {seen[rule.id]}")
                continue
            seen[rule.id] = f.name
            if checks is not None and rule.check is not None:
                params_model = checks.get(rule.check)
                if params_model is None:
                    problems.append(f"{label}: unknown check {rule.check!r}; registered: {sorted(checks)}")
                else:
                    try:
                        params_model.model_validate(rule.params)
                    except ValidationError as e:
                        problems += [
                            f"{label}: params.{'.'.join(map(str, err['loc']))}: {err['msg']}"
                            for err in e.errors()
                        ]
            rules.append(rule)
    if problems:
        raise RulebookError(problems)
    return Rulebook(version=_version(files), rules=rules)


def new_finding(
    rule: Rule | None,
    *,
    reviewer: str,
    evidence: list[EvidenceRef],
    comment: str,
    recommended_correction: str | None = None,
    result: Literal["fail", "warning"] | None = None,
    source: Source | None = None,
    category: Category | None = None,
    requirement: str | None = None,
) -> Finding:
    """Build a finding the safe way: category, requirement, severity and source come from the rule.

    With a rule: the result defaults to `fail` for code/lookup rules and `warning` for LLM rules.
    Without a rule (an LLM observation no rule covers): pass `category` and `requirement`; it becomes a
    warning with severity `info`.
    """
    if rule is None:
        if category is None or requirement is None:
            raise ValueError("a finding without a rule needs a category and a requirement")
        return Finding(
            rule_id=None,
            category=category,
            requirement=requirement,
            result="warning",
            severity="info",
            evidence=evidence,
            comment=comment,
            recommended_correction=recommended_correction,
            reviewer=reviewer,
            source=source or "llm",
        )
    return Finding(
        rule_id=rule.id,
        category=rule.category,
        requirement=rule.requirement,
        result=result or ("fail" if rule.can_fail else "warning"),
        severity=rule.severity,
        evidence=evidence,
        comment=comment,
        recommended_correction=recommended_correction,
        reviewer=reviewer,
        source=source or rule.check_type,
    )
