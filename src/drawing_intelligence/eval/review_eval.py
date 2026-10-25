"""`di eval review`: how good the review is, measured on the planted-error drawings (A5a's answer keys).

Every case runs through the whole workflow (intake -> understand -> reviewers -> verify), each in its own
session in a temporary folder, so `data/sessions/` is never touched.

**When does a finding catch a planted error?** When its rule is the key's rule (or one of its
`also_acceptable` rules) and it cites the same evidence: at least one identical evidence key
(`page:kind:ref`, e.g. `1:dimension:D6`), or, for `text` and `region` evidence, which have no stable id, any
overlap of the two bboxes on the same page.

**Every finding is labelled:**
- `caught`: it catches a planted error, as above;
- `acceptable`: an `also_acceptable` rule that does not cite the key's evidence: caused by the planted error,
  so not a false alarm, but not a catch either;
- `pre_existing`: a real issue in the client's original drawing (same rule and evidence as in the key);
- `false_alarm`: anything else, including any finding on a near-miss case's `must_not_flag` rules.

**Recall** is reported twice: over every planted error (coverage of the rulebook), and over the planted errors
whose rule (or an acceptable one) has a built check (quality of the checks that exist). **Precision** is the
share of findings that are not false alarms, overall and per reviewer.

**False alarms on clean and near-miss drawings** are counted separately for code and LLM findings
(2026-10-25). A code false alarm is a bug to fix; LLM warnings are measured and tuned, not a gate (Spike E:
32-61% precision).
"""

from __future__ import annotations

import shutil
import tempfile
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from drawing_intelligence.eval.answer_key import AnswerKey, ExpectedFinding, load_answer_keys
from drawing_intelligence.schemas import EvidenceRef, Finding, ReviewResult
from drawing_intelligence.settings import Settings

Label = Literal["caught", "acceptable", "pre_existing", "false_alarm"]
CORRECT: frozenset[str] = frozenset({"caught", "acceptable", "pre_existing"})


def _overlap(a: list[float] | None, b: list[float] | None) -> bool:
    if not a or not b:
        return False
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


_LOOSE = ("text", "region")  # no stable id: matched by bbox overlap, never by their quote


def same_evidence(found: list[EvidenceRef], expected: list[EvidenceRef]) -> bool:
    """At least one identical evidence key, or overlapping bboxes for text and region evidence."""
    keys = {e.key() for e in expected if e.kind not in _LOOSE}
    if any(e.key() in keys for e in found if e.kind not in _LOOSE):
        return True
    loose = [e for e in expected if e.kind in _LOOSE]
    return any(
        f.page == x.page and _overlap(f.bbox, x.bbox) for f in found if f.kind in _LOOSE for x in loose
    )


def label(f: Finding, key: AnswerKey) -> Label:
    for x in key.expected:
        if f.rule_id in {x.rule_id, *x.also_acceptable} and same_evidence(f.evidence, x.evidence):
            return "caught"
    if any(f.rule_id in x.also_acceptable for x in key.expected):
        return "acceptable"
    if any(f.rule_id == x.rule_id and same_evidence(f.evidence, x.evidence) for x in key.pre_existing):
        return "pre_existing"
    return "false_alarm"


@dataclass
class CaseScore:
    case: str
    kind: str
    expected: list[ExpectedFinding]
    caught: list[bool]  # one per expected finding
    covered: list[bool]  # one per expected finding: its rule (or an acceptable one) has a built check
    labels: list[tuple[Finding, Label]]
    cost_usd: float = 0.0
    latency_s: float = 0.0

    @property
    def false_alarms(self) -> list[Finding]:
        return [f for f, lab in self.labels if lab == "false_alarm"]


def score_case(key: AnswerKey, review: ReviewResult, built_rules: set[str]) -> CaseScore:
    labels: list[tuple[Finding, Label]] = [(f, label(f, key)) for f in review.findings]
    caught = [
        any(
            f.rule_id in {x.rule_id, *x.also_acceptable} and same_evidence(f.evidence, x.evidence)
            for f in review.findings
        )
        for x in key.expected
    ]
    covered = [bool({x.rule_id, *x.also_acceptable} & built_rules) for x in key.expected]
    return CaseScore(
        key.case, key.kind, key.expected, caught, covered, labels, review.cost_usd, review.latency_s
    )


@dataclass
class Summary:
    planted: int
    caught: int
    covered: int
    caught_covered: int
    findings: int
    correct: int
    false_alarms_on_quiet: list[tuple[str, Finding]] = field(
        default_factory=list
    )  # code findings, clean+near-miss
    llm_alarms_on_quiet: list[tuple[str, Finding]] = field(
        default_factory=list
    )  # LLM warnings there: measured only
    by_category: dict[str, tuple[int, int]] = field(default_factory=dict)  # category -> (caught, planted)
    by_reviewer: dict[str, tuple[int, int]] = field(default_factory=dict)  # reviewer -> (correct, findings)
    labels: Counter[str] = field(default_factory=Counter)

    @property
    def recall(self) -> float | None:
        return self.caught / self.planted if self.planted else None

    @property
    def recall_covered(self) -> float | None:
        return self.caught_covered / self.covered if self.covered else None

    @property
    def precision(self) -> float | None:
        return self.correct / self.findings if self.findings else None


def summarize(scores: Iterable[CaseScore]) -> Summary:
    scores = list(scores)
    s = Summary(0, 0, 0, 0, 0, 0)
    cats: dict[str, list[int]] = {}
    revs: dict[str, list[int]] = {}
    for c in scores:
        for x, hit, cov in zip(c.expected, c.caught, c.covered, strict=True):
            s.planted += 1
            s.caught += hit
            s.covered += cov
            s.caught_covered += hit and cov
            cat = cats.setdefault(x.category, [0, 0])
            cat[0] += hit
            cat[1] += 1
        for f, lab in c.labels:
            s.findings += 1
            s.correct += lab in CORRECT
            s.labels[lab] += 1
            rev = revs.setdefault(f.reviewer, [0, 0])
            rev[0] += lab in CORRECT
            rev[1] += 1
        if c.kind in ("clean", "near_miss"):
            s.false_alarms_on_quiet += [(c.case, f) for f in c.false_alarms if f.source != "llm"]
            s.llm_alarms_on_quiet += [(c.case, f) for f in c.false_alarms if f.source == "llm"]
    s.by_category = {k: (v[0], v[1]) for k, v in sorted(cats.items())}
    s.by_reviewer = {k: (v[0], v[1]) for k, v in sorted(revs.items())}
    return s


def built_rule_ids(rules_dir: Path) -> set[str]:
    """Rules whose check function exists (code and lookup rules only, for now)."""
    from drawing_intelligence.review import load_rulebook
    from drawing_intelligence.review.checks import param_models

    checks = param_models()
    return {r.id for r in load_rulebook(rules_dir, checks=checks).rules if r.check in checks}


def run_review_eval(
    settings: Settings,
    cases_dir: Path | None = None,
    *,
    understand: bool = True,
    llm_review: bool = True,
    only: list[str] | None = None,
    model: str | None = None,
    thinking: str | None = None,
    review_model: str | None = None,
    review_thinking: str | None = None,
) -> list[CaseScore]:
    """Review every seeded case through the full workflow and score it against its key.

    Sessions live in a temporary folder that is deleted afterwards. Retention is `keep` there, so the
    understanding step reads and fills the shared response cache (`data/cache/`): a re-run costs nothing.
    """
    from drawing_intelligence.graph import run_workflow

    root = cases_dir or settings.data_path / "eval" / "seeded"
    keys = [k for k in load_answer_keys(root) if not only or any(k.case.startswith(o) for o in only)]
    built = built_rule_ids(settings.config_path / "rules")
    tmp = Path(tempfile.mkdtemp(prefix="di-eval-"))
    run_settings = settings.model_copy(update={"sessions_root": tmp / "sessions", "retention": "keep"})
    try:
        scores = []
        for key in keys:
            res = run_workflow(
                root / key.case / key.pdf,
                run_settings,
                understand=understand,
                review=True,
                llm_review=llm_review,
                model=model,
                thinking=thinking,
                review_model=review_model,
                review_thinking=review_thinking,
            )
            assert res.review is not None
            score = score_case(key, res.review, built)
            score.cost_usd += sum(r.cost_usd for r in res.understanding if not r.cached)
            score.latency_s += sum(r.latency_s for r in res.understanding if not r.cached)
            scores.append(score)
        return scores
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
