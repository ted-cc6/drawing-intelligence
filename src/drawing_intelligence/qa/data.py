"""What the Q&A agent knows about one reviewed drawing: the saved results, indexed by citable ID (ADR 0011).

Every item the agent can cite has one key, written the same way in tool results and in answers:

    D12  dimension (stage 1, exact)        S3  symbol (stage 1, exact)       L7  text line (stage 1, exact)
    N2   note as the vision pass read it   F4  finding 4 of the report       TB:material  title-block field
    R:WST-207  a rule                      T:...  a reference-table lookup (made by `lookup_standard`)

Items on sheet 2 onwards carry the sheet: `p2:D12`, `p2:TB:revision`. Text lines are numbered in reading order
per sheet. Nothing here calls a model; the data are the saved JSON of a finished review.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from drawing_intelligence.extraction import load_template
from drawing_intelligence.extraction.template import Template
from drawing_intelligence.report.build import location, numbered
from drawing_intelligence.report.zones import markers, zone
from drawing_intelligence.review import load_rulebook
from drawing_intelligence.review.reference import load_reference
from drawing_intelligence.review.rulebook import Rule, Rulebook
from drawing_intelligence.schemas import DrawingKnowledge, Extraction, Finding, PageExtraction, ReviewResult
from drawing_intelligence.settings import Settings


@dataclass(frozen=True)
class Item:
    """One citable thing on the drawing."""

    cite: str
    kind: str  # dimension | symbol | line | note | title_block
    page: int
    text: str
    bbox: list[float] | None
    provenance: str
    obj: Any = None  # the schema object behind it


def qualify(page: int, local: str) -> str:
    return local if page == 1 else f"p{page}:{local}"


@dataclass
class DrawingData:
    extraction: Extraction
    knowledge: dict[int, DrawingKnowledge | None]
    review: ReviewResult
    rulebook: Rulebook
    reference: dict[str, Any]
    template: Template
    items: dict[str, Item] = field(default_factory=dict)
    findings: dict[int, Finding] = field(default_factory=dict)
    _markers: dict[int, tuple[dict, dict]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for page in self.extraction.pages:
            self._markers[page.page_number] = markers(page, self.template)
            self._index(page)
        self.findings = {nf.no: nf.finding for nf in numbered(self.review)}

    @property
    def pages(self) -> dict[int, PageExtraction]:
        return {p.page_number: p for p in self.extraction.pages}

    def _add(self, page: int, local: str, kind: str, text: str, bbox: Any, provenance: str, obj: Any) -> None:
        cite = qualify(page, local)
        self.items[cite] = Item(cite, kind, page, text, list(bbox) if bbox else None, provenance, obj)

    def _index(self, page: PageExtraction) -> None:
        n = page.page_number
        for d in page.dimensions:
            if d.id:
                self._add(n, d.id, "dimension", d.text, d.bbox, "pdf_text", d)
        for s in page.symbols:
            self._add(n, s.id, "symbol", s.text, s.bbox, s.provenance, s)
        for i, line in enumerate(page.body_text, 1):
            self._add(n, f"L{i}", "line", line.text, line.bbox, "pdf_text", line)
        for name, f in page.title_block_fields.items():
            self._add(n, f"TB:{name}", "title_block", f.value or "", f.bbox, "pdf_text", f)
        k = self.knowledge.get(n)
        for note in k.notes if k else []:
            self._add(n, note.id, "note", note.text, None, "vision", note)

    def zone_of(self, page: int, bbox: list[float] | None) -> str | None:
        p = self.pages.get(page)
        return zone(p, self.template, bbox, self._markers.get(page)) if p else None

    def where(self, item: Item) -> str:
        z = self.zone_of(item.page, item.bbox)
        return f"sheet {item.page}" + (f", zone {z}" if z else "")

    def rule(self, rule_id: str) -> Rule | None:
        return next((r for r in self.rulebook.rules if r.id == rule_id), None)

    def rule_status(self, rule_id: str) -> tuple[str, str | None]:
        s = next((s for s in self.review.rule_statuses if s.rule_id == rule_id), None)
        return (s.status, s.note) if s else ("not_checked", "not in this review")

    def finding_location(self, f: Finding) -> str:
        return location(f, self.extraction, self.template)

    def overview(self) -> str:
        """The compact picture of the drawing that opens every conversation."""
        out = [f"Drawing file: {Path(self.extraction.source_file).name}; {self.extraction.n_pages} sheet(s)."]
        for page in self.extraction.pages:
            w, h = page.page_size_pts
            fields = ", ".join(
                f"[{qualify(page.page_number, 'TB:' + k)}] {v.value}"
                for k, v in page.title_block_fields.items()
                if v.value
            )
            out.append(
                f"Sheet {page.page_number} ({w:.0f} x {h:.0f} pt): {len(page.dimensions)} dimensions (D), "
                f"{len(page.symbols)} symbols (S), {len(page.body_text)} text lines (L)."
            )
            if fields:
                out.append(f"Title block, sheet {page.page_number}: {fields}")
        counts: dict[str, int] = {}
        for s in self.review.rule_statuses:
            counts[s.status] = counts.get(s.status, 0) + 1
        out.append(
            "Review: "
            + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in sorted(counts.items()))
            + f" (of {len(self.review.rule_statuses)} rules)."
        )
        out.append(f"Findings ({len(self.findings)}), in report order:")
        for no, f in self.findings.items():
            out.append(
                f"[F{no}] {f.result}, {f.severity}, {f.rule_id or '-'} ({_checked_by(f)}): {f.comment} "
                f"-- {self.finding_location(f)}"
            )
        return "\n".join(out)

    # --- saved form (for `di ask --keep` / `--session`) ----------------------------------------------------

    def save(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "extraction.json").write_text(self.extraction.model_dump_json(), encoding="utf-8")
        (folder / "review_result.json").write_text(self.review.model_dump_json(), encoding="utf-8")
        knowledge = {str(k): v.model_dump(mode="json") if v else None for k, v in self.knowledge.items()}
        (folder / "knowledge.json").write_text(json.dumps(knowledge), encoding="utf-8")

    @classmethod
    def load(cls, folder: Path, settings: Settings) -> DrawingData:
        ex = Extraction.model_validate_json((folder / "extraction.json").read_text(encoding="utf-8"))
        review = ReviewResult.model_validate_json((folder / "review_result.json").read_text(encoding="utf-8"))
        raw = json.loads((folder / "knowledge.json").read_text(encoding="utf-8"))
        knowledge = {int(k): DrawingKnowledge.model_validate(v) if v else None for k, v in raw.items()}
        return cls.build(ex, knowledge, review, settings)

    @classmethod
    def build(
        cls,
        extraction: Extraction,
        knowledge: dict[int, DrawingKnowledge | None],
        review: ReviewResult,
        settings: Settings,
    ) -> DrawingData:
        return cls(
            extraction=extraction,
            knowledge=knowledge,
            review=review,
            rulebook=load_rulebook(settings.config_path / "rules"),
            reference=load_reference(settings.config_path / "reference"),
            template=load_template(extraction.template, settings.config_path),
        )


def _checked_by(f: Finding) -> str:
    return {"code": "code check", "lookup": "table lookup", "llm": "AI reviewer"}[f.source]


_CITE = re.compile(r"^(?:p(\d+):)?(.+)$")


def split_cite(cite: str) -> tuple[int, str]:
    m = _CITE.match(cite)
    assert m
    return (int(m[1]) if m[1] else 1), m[2]
