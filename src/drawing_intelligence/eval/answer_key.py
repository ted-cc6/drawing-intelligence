"""Answer keys for the planted-error drawings (A5a): what a correct review of each seeded case reports.

Every case folder in `data/eval/seeded/` holds an `expected_findings.json`. The keys were written by hand from
the approved case list, before any reviewer existed, and are never changed to fit a reviewer's output.
Category, severity and result are the rule's own (from the rulebook: an `llm` rule gives a warning, the others
a fail). Evidence is the A2 `EvidenceRef`, with the ids of the *seeded* PDF's extraction: a removed dimension
shifts the ids after it. Notes are `text` evidence with their quote, because note ids (N1...) come from the
model.

- `expected`: the planted error, under its rule. `also_acceptable` names other rules the same change breaks: a
  finding under one of them is caused by the planted error, so it is not a false alarm, and when it cites the
  key's evidence it catches the error too.
- `must_not_flag` (near-miss cases only): rules that must stay quiet on a change that is still correct.
- `pre_existing`: issues already in the client's original drawing, the same in every case built from it. A
  finding on one of them is right, not a false alarm, but it does not catch the planted error.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from drawing_intelligence.schemas.review import Category, EvidenceRef, Severity

ANSWER_KEY_SCHEMA_VERSION = "1.0"
KEY_FILE = "expected_findings.json"

Kind = Literal["planted", "near_miss", "clean"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExpectedFinding(_Strict):
    """A finding a correct review reports."""

    rule_id: str
    category: Category
    severity: Severity
    result: Literal["fail", "warning"]
    evidence: list[EvidenceRef] = Field(min_length=1)
    description: str
    also_acceptable: list[str] = []


class NotAFinding(_Strict):
    """A near-miss: a change that is still correct, which these rules must not flag."""

    rule_ids: list[str] = Field(min_length=1)
    evidence: list[EvidenceRef] = Field(min_length=1)
    description: str


class AnswerKey(_Strict):
    """The answer key of one seeded case."""

    schema_version: Literal["1.0"] = ANSWER_KEY_SCHEMA_VERSION
    case: str
    kind: Kind
    base: str = Field(description="the sample in data/raw the case was built from")
    pdf: str
    planted: str = Field(description="what was changed, in words")
    expected: list[ExpectedFinding] = []
    must_not_flag: list[NotAFinding] = []
    pre_existing: list[ExpectedFinding] = []

    @model_validator(mode="after")
    def _fits_kind(self) -> AnswerKey:
        if (self.kind == "planted") != bool(self.expected):
            raise ValueError(f"{self.case}: planted cases, and only they, expect findings")
        if (self.kind == "near_miss") != bool(self.must_not_flag):
            raise ValueError(f"{self.case}: near-miss cases, and only they, list must_not_flag")
        return self


def load_answer_keys(root: Path) -> list[AnswerKey]:
    """The key of every case folder under `root` (data/eval/seeded), in case order."""
    folders = sorted(d for d in root.iterdir() if (d / KEY_FILE).is_file())
    return [AnswerKey.model_validate_json((d / KEY_FILE).read_text(encoding="utf-8")) for d in folders]
