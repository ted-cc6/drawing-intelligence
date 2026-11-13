"""What a drawing specifies for heat treatment and plating, read from the title block and the notes.

PARI's title block usually says '---' or 'REF NOTE' for the heat treatment and the notes carry it ("1) TO BE
TOUGHENED UPTO 28-32 HRC."), so both are read. Only the exact text is used; anything not understood is left
out, never guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from drawing_intelligence.review.checks import _evidence as ev
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.reference import PlatingProcess, PlatingProcesses
from drawing_intelligence.review.reference_des11 import Material, MaterialHeatTreatment, Process
from drawing_intelligence.schemas import EvidenceRef, PageExtraction

# DES-11's six columns. "TO BE HARDENED UPTO 32-35 HRC" (no process named) is read as through hardening.
PROCESS_TERMS: dict[Process, re.Pattern[str]] = {
    "case": re.compile(r"CASE[\s-]*HARDEN|(?<!NITRO)CARBURI[SZ]|CASE\s+CARB", re.I),
    "nitriding": re.compile(r"NITRID|NITROCARBURI[SZ]", re.I),
    "induction": re.compile(r"INDUCTION", re.I),
    "flame": re.compile(r"FLAME[\s-]*HARDEN", re.I),
    "toughening": re.compile(r"TOUGHE?N|HARDENED\s*(?:AND|&)\s*TEMPERED", re.I),
    "through": re.compile(
        r"THROUGH[\s-]*HARDEN|(?<!CASE )(?<!CASE)\bHARDENED\b(?!\s*(?:AND|&)\s*TEMPER)", re.I
    ),
}
_NUM = r"(\d+(?:\.\d+)?)"
# 28-32 HRC, 56~60 HRC, 30 TO 32 HRC, 24 -32 HRC; 58±2 HRC (PARI's text layer prints ± as 'u')
_HRC_RANGE = re.compile(_NUM + r"\s*(?:-|~|–|TO)\s*" + _NUM + r"\s*HRC", re.I)
_HRC_PLUS_MINUS = re.compile(_NUM + r"\s*(?:±|u|\+/-)\s*" + _NUM + r"\s*HRC", re.I)
_CASE_DEPTH = re.compile(r"DEPTH\D{0,12}?" + _NUM + r"\s*(?:-|~|–|TO)\s*" + _NUM + r"\s*MM", re.I)
_FLASH = re.compile(r"FLASH", re.I)


@dataclass(frozen=True)
class Spec:
    """One piece of text that specifies a treatment, and where it is."""

    page: PageExtraction
    text: str
    evidence: EvidenceRef


def specs(ctx: ReviewContext) -> list[Spec]:
    """The title block's heat and surface treatment fields (when not a placeholder) and every body line."""
    out = []
    for page in ctx.pages:
        for name in ("heat_treatment", "surface_treatment"):
            value = ev.value(page, name)
            if value and not ev.is_placeholder(value):
                out.append(Spec(page, value, ev.field(page, name)))
        seen = set()
        for line in [*page.notes, *page.body_text]:
            key = (line.text, tuple(round(v) for v in line.bbox))
            if key not in seen:
                seen.add(key)
                out.append(Spec(page, line.text, ev.text(page, line)))
    return out


def processes(text: str) -> list[Process]:
    """The DES-11 processes a text names. A bare HARDENED is through hardening only when nothing else is named
    ("INDUCTION HARDENED", "CASE HARDENED" are not through hardening)."""
    named: list[Process] = [p for p, pattern in PROCESS_TERMS.items() if pattern.search(text)]
    return named if named == ["through"] else [p for p in named if p != "through"]


def hrc_range(text: str) -> tuple[float, float] | None:
    if m := _HRC_PLUS_MINUS.search(text):
        mid, tol = float(m[1]), float(m[2])
        return mid - tol, mid + tol
    if m := _HRC_RANGE.search(text):
        low, high = sorted((float(m[1]), float(m[2])))
        return low, high
    return None


def case_depth_mm(text: str) -> tuple[float, float] | None:
    if m := _CASE_DEPTH.search(text):
        low, high = sorted((float(m[1]), float(m[2])))
        return low, high
    return None


@dataclass(frozen=True)
class HeatTreatment:
    process: Process
    spec: Spec
    hrc: tuple[float, float] | None
    depth_mm: tuple[float, float] | None

    @property
    def inferred(self) -> bool:
        """A bare HARDENED: read as through hardening, but the drawing does not name the process."""
        return self.process == "through" and not re.search(r"THROUGH", self.spec.text, re.I)


def heat_treatments(ctx: ReviewContext) -> list[HeatTreatment]:
    """Each heat treatment the drawing names. A hardness or depth on a line of its own ("HARDNESS & DEPTH :
    59±2 HRC") is given to the drawing's process when it names exactly one."""
    found: list[HeatTreatment] = []
    loose: list[Spec] = []
    for s in specs(ctx):
        named = processes(s.text)
        if named:
            found += [HeatTreatment(p, s, hrc_range(s.text), case_depth_mm(s.text)) for p in named]
        elif hrc_range(s.text) or case_depth_mm(s.text):
            loose.append(s)
    if len({h.process for h in found}) == 1 and loose:
        h = found[0]
        hrc = h.hrc or next((r for s in loose if (r := hrc_range(s.text))), None)
        depth = h.depth_mm or next((d for s in loose if (d := case_depth_mm(s.text))), None)
        found = [HeatTreatment(x.process, x.spec, x.hrc or hrc, x.depth_mm or depth) for x in found]
    return found


@dataclass(frozen=True)
class Plating:
    process: PlatingProcess
    spec: Spec


def platings(ctx: ReviewContext, table: PlatingProcesses) -> list[Plating]:
    """Each DES-12 process the drawing names. "FLASH HARD CHROME" is flash chrome, not hard chrome."""
    out = []
    for s in specs(ctx):
        process = table.identify(s.text)
        if process and _FLASH.search(s.text):
            process = next((p for p in table.processes if p.id == "flash_chrome"), process)
        if process:
            out.append(Plating(process, s))
    return out


# "# MATERIAL : EN9", "## 2) MATL :- En-24", "MATERIAL :- 20MnCr5"; not "RAW MATERIAL" or a revision row
_MATERIAL_NOTE = re.compile(r"^[\W\d)]*(?:MATERIAL|MATL)\s*:\s*-?\s*(.+)$", re.I)


@dataclass(frozen=True)
class MaterialRows:
    text: str
    evidence: EvidenceRef
    rows: list[Material]


def des11_rows(ctx: ReviewContext, table: MaterialHeatTreatment) -> MaterialRows | None:
    """The DES-11 rows the drawing's material matches: the title block's, else the '# MATERIAL :' note.

    One designation can match two rows (C45 is a row and one of EN9's equivalents), and "EN9/C45" names two
    grades; every row any part matches is returned, so a check judges only when the rows agree.
    """
    found: list[tuple[str, EvidenceRef]] = []
    for page in ctx.pages:
        material = ev.value(page, "material")
        if material and not ev.is_placeholder(material):
            found.append((material, ev.field(page, "material")))
        for line in page.body_text:
            if m := _MATERIAL_NOTE.match(line.text):
                found.append((m[1].strip(), ev.text(page, line)))
    for text, evidence in found:
        rows: list[Material] = []
        for part in re.split(r"[/,]| OR ", text):
            rows += [r for r in table.candidates(part.strip()) if r not in rows]
        if rows:
            return MaterialRows(text, evidence, rows)
    return None
