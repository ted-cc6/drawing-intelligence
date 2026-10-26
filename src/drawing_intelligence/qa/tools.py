"""The Q&A agent's tools (ADR 0011): read-only views of one reviewed drawing, plus the feedback log.

Each tool takes JSON arguments and returns a JSON-able dict. Everything citable carries its `cite` key, the
form an answer must use. Bad arguments come back as {"error", "hint"}, never as an exception, so the model
can correct itself. Lists stop at `MAX_ITEMS` with `"more": N`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from drawing_intelligence.qa.data import DrawingData, Item, split_cite
from drawing_intelligence.review.checks._tolerance import parse as parse_tolerance
from drawing_intelligence.review.checks.fits import parse_fit
from drawing_intelligence.review.reference import (
    FitDeviations,
    GeneralTolerances,
    Materials,
    MetricThreads,
    PlatingProcesses,
)
from drawing_intelligence.schemas import SymbolItem, TextItem, TitleBlockField
from drawing_intelligence.schemas.knowledge import Note

MAX_ITEMS = 30
VERDICTS = ("correct", "incorrect", "unsure")


class ToolError(Exception):
    def __init__(self, error: str, hint: str):
        super().__init__(error)
        self.hint = hint


@dataclass
class ToolBox:
    """The tools bound to one drawing. `lookups` collects the T: keys this conversation has produced."""

    data: DrawingData
    feedback_path: Path | None = None
    lookups: set[str] = field(default_factory=set)
    feedback_allowed: bool = False  # set per question: only the engineer's own message may ask for it

    def call(self, name: str, arguments: str | dict[str, Any]) -> dict[str, Any]:
        fn: Callable[..., dict[str, Any]] | None = getattr(self, f"t_{name}", None)
        if fn is None:
            return {
                "error": f"no tool {name!r}",
                "hint": f"tools: {', '.join(t['function']['name'] for t in SCHEMAS)}",
            }
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
            if not isinstance(args, dict):
                raise ToolError("arguments must be a JSON object", "pass named arguments")
            return fn(**args)
        except ToolError as e:
            return {"error": str(e), "hint": e.hint}
        except (TypeError, ValueError) as e:
            return {"error": f"bad arguments: {e}", "hint": "check the tool's parameters"}

    # --- findings and rules ---------------------------------------------------------------------------------

    def t_list_findings(
        self, severity: str | None = None, category: str | None = None, rule: str | None = None
    ) -> dict:
        rows = [
            {
                "cite": f"F{no}",
                "result": f.result,
                "severity": f.severity,
                "rule": f.rule_id,
                "category": f.category,
                "checked_by": f.source,
                "comment": f.comment,
            }
            for no, f in self.data.findings.items()
            if (not severity or f.severity == severity)
            and (not category or f.category == category)
            and (not rule or (f.rule_id or "").upper() == rule.upper())
        ]
        return _page(rows, "findings")

    def t_get_finding(self, no: int | str) -> dict:
        n = int(str(no).lstrip("Ff"))
        f = self.data.findings.get(n)
        if f is None:
            raise ToolError(f"no finding F{n}", f"findings are F1 to F{len(self.data.findings)}")
        rule = self.data.rule(f.rule_id) if f.rule_id else None
        evidence = []
        for e in f.evidence:
            cite = self._cite_for(e.kind, e.ref, e.page)
            evidence.append(
                {
                    "cite": cite,
                    "kind": e.kind,
                    "quote": e.quote,
                    "sheet": e.page,
                    "zone": self.data.zone_of(e.page, e.bbox),
                    "provenance": e.provenance,
                }
            )
        return {
            "cite": f"F{n}",
            "result": f.result,
            "severity": f.severity,
            "category": f.category,
            "rule": _rule_summary(rule) if rule else None,
            "requirement": f.requirement,
            "comment": f.comment,
            "recommended_correction": f.recommended_correction,
            "checked_by": f.source,
            "reviewer": f.reviewer,
            "evidence": evidence,
            "location": self.data.finding_location(f),
            "trust": "code and table checks are exact; AI reviewer findings are warnings to confirm",
        }

    def t_get_rule(self, rule_id: str) -> dict:
        rule = self.data.rule(rule_id.strip().upper())
        if rule is None:
            raise ToolError(f"no rule {rule_id!r}", "use search_rules to find a rule by topic")
        status, note = self.data.rule_status(rule.id)
        return {
            **_rule_summary(rule),
            "status_on_this_drawing": status,
            "status_note": note,
            "findings": [f"F{no}" for no, f in self.data.findings.items() if f.rule_id == rule.id],
        }

    def t_search_rules(self, query: str, category: str | None = None) -> dict:
        words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 2]
        if not words:
            raise ToolError(
                "query is empty", "give a topic, e.g. 'thread', 'fit tolerance', 'title block date'"
            )
        scored = []
        for r in self.data.rulebook.rules:
            if category and r.category != category:
                continue
            hay = f"{r.id} {r.category} {r.requirement} {r.check or ''}".lower()
            score = sum(w in hay for w in words)
            if score:
                scored.append((-score, r.id, r))
        rows = []
        for _, _, r in sorted(scored):
            status, _ = self.data.rule_status(r.id)
            rows.append(
                {
                    "cite": f"R:{r.id}",
                    "category": r.category,
                    "requirement": r.requirement,
                    "status_on_this_drawing": status,
                }
            )
        return _page(rows, "rules")

    # --- the drawing ----------------------------------------------------------------------------------------

    def t_search_drawing(
        self,
        text: str | None = None,
        kind: str | None = None,
        sheet: int | None = None,
        zone: str | None = None,
    ) -> dict:
        kinds = {"dimension", "symbol", "line", "note", "title_block"}
        if kind and kind not in kinds:
            raise ToolError(f"unknown kind {kind!r}", f"kind is one of {sorted(kinds)}")
        want = _squash(text or "")
        rows = []
        for item in self.data.items.values():
            if (kind and item.kind != kind) or (sheet and item.page != sheet):
                continue
            z = self.data.zone_of(item.page, item.bbox)
            if zone and (z or "").upper() != zone.upper():
                continue
            if want and want not in _squash(item.text) and want not in item.cite.upper():
                continue
            rows.append(
                {"cite": item.cite, "kind": item.kind, "text": item.text, "sheet": item.page, "zone": z}
            )
        return _page(rows, "items")

    def t_get_items(self, ids: list[str] | str) -> dict:
        wanted = [ids] if isinstance(ids, str) else ids
        out, missing = [], []
        for raw in wanted[:MAX_ITEMS]:
            cite = raw.strip().strip("[]")
            item = self.data.items.get(cite)
            if item is None:
                missing.append(cite)
                continue
            out.append(self._detail(item))
        result: dict[str, Any] = {"items": out}
        if missing:
            result["not_found"] = missing
            result["hint"] = (
                "IDs are as printed by search_drawing (D12, S3, L7, N2, TB:material; p2:D4 on sheet 2)"
            )
        return result

    def _detail(self, item: Item) -> dict:
        d: dict[str, Any] = {
            "cite": item.cite,
            "kind": item.kind,
            "text": item.text,
            "sheet": item.page,
            "zone": self.data.zone_of(item.page, item.bbox),
            "provenance": item.provenance,
        }
        obj = item.obj
        if isinstance(obj, TextItem):
            d["is_reference"] = obj.is_reference
            if obj.limits:
                d["printed_limits"] = {"upper": obj.limits[0], "lower": obj.limits[1]}
            t = parse_tolerance(obj)
            if t and t.upper is not None and t.lower is not None:
                d["tolerance"] = {
                    "nominal": t.nominal_text,
                    "upper_deviation": _num(t.upper),
                    "lower_deviation": _num(t.lower),
                    "limits_of_size": [_num(t.nominal + t.lower), _num(t.nominal + t.upper)],
                }
            fit = parse_fit(obj.text)
            if fit:
                d["fit"] = self._fit(fit[1], fit[0], quiet=True)
            k = self.data.knowledge.get(item.page)
            vision = next((x for x in (k.dimensions if k else []) if x.id == split_cite(item.cite)[1]), None)
            if vision:
                d["vision"] = {
                    "type": vision.type,
                    "feature": vision.feature_id,
                    "view": vision.view_id,
                    "note": "from the vision pass: approximate",
                }
                feat = next((f for f in k.features if f.id == vision.feature_id), None) if k else None
                if feat:
                    d["vision"]["feature_description"] = feat.description
        elif isinstance(obj, SymbolItem):
            d.update(
                {
                    "symbol_type": obj.type,
                    "characteristic": obj.characteristic,
                    "tolerance": obj.tolerance,
                    "datums": obj.datums,
                    "ra": obj.ra,
                }
            )
        elif isinstance(obj, TitleBlockField):
            d["read_from"] = "the title-block cell" if obj.source == "cell" else "the '#' notes block"
        elif isinstance(obj, Note):
            d["category"] = obj.category
        return d

    def _cite_for(self, kind: str, ref: str | None, page: int) -> str | None:
        local = {
            "dimension": ref,
            "symbol": ref,
            "note": ref,
            "title_block": f"TB:{ref}" if ref else None,
        }.get(kind)
        if local is None:
            return None
        cite = local if page == 1 else f"p{page}:{local}"
        return cite if cite in self.data.items else None

    # --- standards ------------------------------------------------------------------------------------------

    def t_lookup_standard(
        self,
        table: str,
        zone: str | None = None,
        size: float | None = None,
        pitch: float | None = None,
        kind: str | None = None,
        tolerance_class: str | None = None,
        designation: str | None = None,
        treatment: str | None = None,
    ) -> dict:
        if table == "fit":
            if not zone or size is None:
                raise ToolError("fit needs zone and size", "e.g. table='fit', zone='H7', size=20")
            return self._fit(zone, float(size))
        if table == "thread":
            return self._thread(size, pitch)
        if table == "general_tolerance":
            return self._general(size, kind or "linear", tolerance_class)
        if table == "material":
            return self._material(designation)
        if table == "plating":
            return self._plating(treatment)
        raise ToolError(
            f"unknown table {table!r}", "table is fit, thread, general_tolerance, material or plating"
        )

    def _cite(self, key: str) -> str:
        cite = f"T:{key}"
        self.lookups.add(cite)
        return cite

    def _fit(self, zone: str, size: float, quiet: bool = False) -> dict:
        t = self.data.reference.get("is919_fits")
        if not isinstance(t, FitDeviations):
            raise ToolError("the fit table is not loaded", "config/reference/is919_fits.yaml")
        devs = t.deviations(zone, size)
        if devs is None:
            reason = "zone not tabulated" if zone not in t.zones else "size outside 0-500 mm"
            if quiet:
                return {"zone": zone, "in_table": False, "reason": reason}
            raise ToolError(
                f"{zone} at {size:g} mm is not in the IS 919 table ({reason})",
                f"tabulated zones: {', '.join(sorted(t.zones))}",
            )
        upper, lower = devs[0] / 1000, devs[1] / 1000
        return {
            "cite": self._cite(f"is919_fits {zone} {size:g}"),
            "zone": zone,
            "size_mm": size,
            "upper_deviation_mm": _num(upper),
            "lower_deviation_mm": _num(lower),
            "limits_of_size_mm": [_num(size + lower), _num(size + upper)],
            "source": t.source.section,
        }

    def _thread(self, size: float | None, pitch: float | None) -> dict:
        t = self.data.reference.get("iso_metric_threads")
        if not isinstance(t, MetricThreads) or size is None:
            raise ToolError(
                "thread needs size (the nominal diameter, e.g. 8 for M8)", "table='thread', size=8"
            )
        s = t.sizes.get(float(size))
        if s is None:
            return {
                "cite": self._cite(f"iso_metric_threads M{size:g}"),
                "size": f"M{size:g}",
                "standard": False,
                "note": "not an ISO 261 size (table covers M1 to M80)",
            }
        out = {
            "cite": self._cite(f"iso_metric_threads M{size:g}"),
            "size": f"M{size:g}",
            "standard": True,
            "coarse_pitch": s.coarse,
            "fine_pitches": s.fine,
            "source": t.source.section,
            "tolerance_classes": {
                kind: [c for c, d in cls.items() if float(size) >= d]
                for kind, cls in t.tolerance_classes.items()
            },
        }
        if pitch is not None:
            out["pitch_is_standard"] = float(pitch) in t.pitches(float(size))
        return out

    def _general(self, size: float | None, kind: str, tolerance_class: str | None) -> dict:
        t = self.data.reference.get("is2102_general_tolerances")
        if not isinstance(t, GeneralTolerances) or size is None:
            raise ToolError("general_tolerance needs size (mm)", "table='general_tolerance', size=50")
        table = t.linear if kind == "linear" else t.angular
        classes = table.classes()
        names = [tolerance_class] if tolerance_class else list(classes)
        if tolerance_class and tolerance_class not in classes:
            raise ToolError(f"unknown class {tolerance_class!r}", f"classes: {', '.join(classes)}")
        step = next(
            (
                i
                for i, (lo, hi) in enumerate(table.steps_mm)
                if lo is not None and (size >= lo if i == 0 else size > lo) and (hi is None or size <= hi)
            ),
            None,
        )
        if step is None:
            raise ToolError(f"{size:g} mm is outside the IS 2102 steps", "linear covers 0.5 to 20000 mm")
        unit = "mm" if kind == "linear" else "minutes of arc"
        lo, hi = table.steps_mm[step]
        values = {n: classes[n][step] for n in names}
        printed = [
            {
                "sheet": p.page_number,
                "process": r.process,
                "tolerance": r.tolerance,
                "range": f"{r.over:g} to {r.up_to:g}" if r.up_to else f"over {r.over:g}",
            }
            for p in self.data.extraction.pages
            for r in p.general_tolerances
            if r.kind == kind and (size >= r.over) and (r.up_to is None or size <= r.up_to)
        ]
        return {
            "cite": self._cite(f"is2102 {kind} {size:g}"),
            "size": size,
            "kind": kind,
            "step": f"over {lo:g} up to {hi:g}" if hi else f"over {lo:g}",
            "plus_minus": values,
            "unit": unit,
            "printed_on_this_drawing": printed,
            "note": "PARI's template uses medium for machining and coarse for fabrication; the drawing's "
            "printed table is what applies",
            "source": t.source.section,
        }

    def _material(self, designation: str | None) -> dict:
        t = self.data.reference.get("materials")
        if not isinstance(t, Materials) or not designation:
            raise ToolError("material needs designation", "table='material', designation='EN8'")
        cls = t.classify(designation)
        return {
            "cite": self._cite(f"materials {designation}"),
            "designation": designation,
            "class": cls,
            "family": t.family(cls),
            "recognised": cls is not None,
            "source": t.source.section,
        }

    def _plating(self, treatment: str | None) -> dict:
        t = self.data.reference.get("plating_processes")
        if not isinstance(t, PlatingProcesses) or not treatment:
            raise ToolError("plating needs treatment", "table='plating', treatment='IZBP'")
        p = t.identify(treatment)
        return {
            "cite": self._cite(f"plating {treatment}"),
            "treatment": treatment,
            "process": p.name if p else None,
            "suits_materials": p.materials if p else None,
            "recognised": p is not None,
            "source": t.source.document,
        }

    # --- feedback (the one write) ---------------------------------------------------------------------------

    def t_record_feedback(self, no: int | str, verdict: str, reason: str) -> dict:
        if not self.feedback_allowed:
            raise ToolError(
                "feedback can only be recorded when the engineer asks for it",
                "do not call record_feedback unless the engineer's message gives feedback",
            )
        if verdict not in VERDICTS:
            raise ToolError(
                f"verdict must be one of {VERDICTS}", "correct = a real issue, incorrect = a false alarm"
            )
        n = int(str(no).lstrip("Ff"))
        f = self.data.findings.get(n)
        if f is None:
            raise ToolError(f"no finding F{n}", f"findings are F1 to F{len(self.data.findings)}")
        if self.feedback_path is None:
            raise ToolError("no feedback log configured", "feedback is off in this session")
        record = {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "drawing": Path(self.data.extraction.source_file).name,
            "rulebook_version": self.data.review.rulebook_version,
            "finding_no": n,
            "rule": f.rule_id,
            "checked_by": f.source,
            "comment": f.comment,
            "quote": next((e.quote for e in f.evidence if e.quote), None),
            "verdict": verdict,
            "reason": reason,
        }
        self.feedback_path.parent.mkdir(parents=True, exist_ok=True)
        with self.feedback_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return {"recorded": True, "finding": f"F{n}", "verdict": verdict}


def _rule_summary(rule: Any) -> dict:
    return {
        "cite": f"R:{rule.id}",
        "id": rule.id,
        "category": rule.category,
        "requirement": rule.requirement,
        "severity": rule.severity,
        "check_type": rule.check_type,
        "source": f"{rule.source.document}, {rule.source.section}",
    }


def _page(rows: list[dict], what: str) -> dict:
    out: dict[str, Any] = {what: rows[:MAX_ITEMS]}
    if len(rows) > MAX_ITEMS:
        out["more"] = len(rows) - MAX_ITEMS
        out["hint"] = "narrow the search (kind, sheet, zone, text)"
    return out


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text).upper()


def _num(v: float) -> float:
    return round(v, 4) + 0.0  # no -0.0


def _schema(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
                "additionalProperties": False,
            },
        },
    }


SCHEMAS: list[dict[str, Any]] = [
    _schema(
        "list_findings",
        "List the review's findings (F1, F2 ...), optionally filtered.",
        {
            "severity": {"type": "string", "enum": ["critical", "major", "minor", "info"]},
            "category": {"type": "string"},
            "rule": {"type": "string", "description": "rule ID, e.g. WST-207"},
        },
    ),
    _schema(
        "get_finding",
        "One finding in full: rule, evidence with IDs, location, how it was checked.",
        {"no": {"type": "integer", "description": "finding number, 4 for F4"}},
        ["no"],
    ),
    _schema(
        "search_drawing",
        "Find items on the drawing by text, kind, sheet or zone. Returns their IDs.",
        {
            "text": {"type": "string"},
            "kind": {"type": "string", "enum": ["dimension", "symbol", "line", "note", "title_block"]},
            "sheet": {"type": "integer"},
            "zone": {"type": "string", "description": "e.g. C4"},
        },
    ),
    _schema(
        "get_items",
        "Full detail of items by ID: text, tolerance and limits of size, fit, zone, provenance.",
        {"ids": {"type": "array", "items": {"type": "string"}, "description": 'e.g. ["D12", "S3"]'}},
        ["ids"],
    ),
    _schema(
        "get_rule",
        "A rule's requirement, severity, source and its status on this drawing.",
        {"rule_id": {"type": "string"}},
        ["rule_id"],
    ),
    _schema(
        "search_rules",
        "Find rules by topic words.",
        {"query": {"type": "string"}, "category": {"type": "string"}},
        ["query"],
    ),
    _schema(
        "lookup_standard",
        "Look up a reference table: fit (zone, size), thread (size, pitch?), "
        "general_tolerance (size, kind?, tolerance_class?), material (designation), plating (treatment).",
        {
            "table": {
                "type": "string",
                "enum": ["fit", "thread", "general_tolerance", "material", "plating"],
            },
            "zone": {"type": "string"},
            "size": {"type": "number"},
            "pitch": {"type": "number"},
            "kind": {"type": "string", "enum": ["linear", "angular"]},
            "tolerance_class": {"type": "string", "enum": ["fine", "medium", "coarse", "extra coarse"]},
            "designation": {"type": "string"},
            "treatment": {"type": "string"},
        },
        ["table"],
    ),
    _schema(
        "record_feedback",
        "Record the engineer's verdict on a finding. Only when the engineer asks.",
        {
            "no": {"type": "integer"},
            "verdict": {"type": "string", "enum": list(VERDICTS)},
            "reason": {"type": "string"},
        },
        ["no", "verdict", "reason"],
    ),
]
