"""Held-out validation: the review on client drawings nothing was built or tuned on, for an engineer to label.

The planted-error set measures recall, but its precision is optimistic: the checks and the LLM reviewers were
tuned on it. Here the review runs on drawings drawn at random from the client set, after leaving out every
drawing an earlier development sweep looked at (two random samples of 200, seeds 1 and 2, used to tune the
title-block parser and the check thresholds). Each finding goes into a CSV with empty label columns: an
engineer marks it `correct`, `incorrect` or `unsure`, which gives the precision a real review would have.
"""

from __future__ import annotations

import csv
import random
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from drawing_intelligence.report.build import location, numbered
from drawing_intelligence.settings import Settings

DEV_SAMPLE_SEEDS = (1, 2)  # the development sweeps' random samples (2026-10-23 to 10-25)
DEV_SAMPLE_SIZE = 200
LABEL_COLUMNS: tuple[str, ...] = (
    "drawing", "no", "rule", "category", "result", "severity", "checked_by", "comment", "location",
    "label", "label_reason", "labelled_by",
)  # fmt: skip


def client_pdfs(client_dir: Path) -> list[Path]:
    return sorted(p for p in client_dir.rglob("*") if p.suffix.lower() == ".pdf")


def development_sample(client_dir: Path) -> set[Path]:
    """The drawings the development sweeps used, recreated exactly as they were drawn."""
    files = client_pdfs(client_dir)
    seen: set[Path] = set()
    for seed in DEV_SAMPLE_SEEDS:
        random.seed(seed)
        seen |= set(random.sample(files, DEV_SAMPLE_SIZE))
    return seen


def _not_a_drawing(path: Path, client_dir: Path) -> bool:
    """The client set also holds PARI's guideline documents and the template; they are not drawings."""
    folders = path.relative_to(client_dir).parts[:-1]
    return any("guideline" in f.lower() or "template" in f.lower() for f in folders)


def select_heldout(client_dir: Path, n: int, seed: int, samples_dir: Path | None = None) -> list[Path]:
    """`n` drawings at random (fixed seed) from those no development sweep looked at, and none of the sample
    drawings everything was built on (copies of them are in the client set too)."""
    samples = {p.stem.lower() for p in samples_dir.glob("*.pdf")} if samples_dir else set()
    seen = development_sample(client_dir)
    pool = [
        p
        for p in client_pdfs(client_dir)
        if p not in seen and p.stem.lower() not in samples and not _not_a_drawing(p, client_dir)
    ]
    return sorted(random.Random(seed).sample(pool, n))


@dataclass
class HeldoutRun:
    drawing: str
    exported_to: Path | None
    findings: int
    cost_usd: float
    variant_title_block: bool
    error: str | None = None


def run_heldout(
    settings: Settings, drawings: list[Path], out_dir: Path, *, understand: bool = True
) -> list[HeldoutRun]:
    """Review every drawing, export its report to `out_dir/<drawing>/`, and write `out_dir/findings.csv`."""
    from drawing_intelligence.extraction import load_template
    from drawing_intelligence.graph import run_workflow

    tmp = Path(tempfile.mkdtemp(prefix="di-heldout-"))
    run_settings = settings.model_copy(update={"sessions_root": tmp / "sessions", "retention": "keep"})
    runs: list[HeldoutRun] = []
    rows: list[dict[str, object]] = []
    try:
        for pdf in drawings:
            try:
                res = run_workflow(pdf, run_settings, understand=understand, review=True, export_dir=out_dir)
            except Exception as e:  # one unreadable drawing must not stop the run
                runs.append(HeldoutRun(pdf.stem, None, 0, 0.0, False, f"{type(e).__name__}: {e}"))
                continue
            assert res.review is not None
            template = load_template(res.extraction.template)
            cost = res.review.cost_usd + sum(r.cost_usd for r in res.understanding if not r.cached)
            variant = any(p.title_block_layout == "variant" for p in res.extraction.pages)
            runs.append(HeldoutRun(pdf.stem, res.exported_to, len(res.review.findings), cost, variant))
            for nf in numbered(res.review):
                f = nf.finding
                rows.append(
                    {
                        "drawing": pdf.stem,
                        "no": nf.no,
                        "rule": f.rule_id or "",
                        "category": f.category,
                        "result": f.result,
                        "severity": f.severity,
                        "checked_by": f.source if f.source != "llm" else f"llm:{f.reviewer}",
                        "comment": f.comment,
                        "location": location(f, res.extraction, template),
                        "label": "",
                        "label_reason": "",
                        "labelled_by": "",
                    }
                )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "findings.csv").open("w", newline="", encoding="utf-8-sig") as fh:  # opens in Excel
        w = csv.DictWriter(fh, fieldnames=list(LABEL_COLUMNS))
        w.writeheader()
        w.writerows(rows)
    return runs
