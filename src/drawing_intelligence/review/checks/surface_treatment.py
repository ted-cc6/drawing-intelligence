"""Surface finish, coating and heat-treatment checks on the title block and the notes (exact text)."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from drawing_intelligence.review.checks import _evidence as ev
from drawing_intelligence.review.checks import _process as pr
from drawing_intelligence.review.checks._registry import NotApplicable, NotCheckable, check
from drawing_intelligence.review.checks._text import term
from drawing_intelligence.review.checks.threads import threads
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.reference import Materials, PlatingProcesses
from drawing_intelligence.review.reference_des11 import PROCESSES, MaterialHeatTreatment, Process
from drawing_intelligence.review.reference_p2 import Prerequisites
from drawing_intelligence.review.rulebook import Rule, new_finding
from drawing_intelligence.schemas import EvidenceRef, Finding, PageExtraction, TextItem

REVIEWER = "checks"
_REFERS_TO_NOTE = re.compile(r"NOTE", re.IGNORECASE)  # REF NOTE, REFER NOTE, REF.NOTE; not REF. DRG / REF BOM
# Words that make a note a heat-treatment specification, not just its heading.
HEAT_TREATMENT_TERMS = (
    "harden",
    "tough",
    "temper",
    "anneal",
    "normali",
    "carburi",
    "nitrid",
    "case",
    "induction",
    "flame",
    "quench",
    "stress reliev",
    "HRC",
    "HRB",
    "HB",
    "HV",
)


def _notes(page: PageExtraction) -> list[TextItem]:
    return page.notes


class NoteParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str


@check("referenced_note_exists", NoteParams)
def referenced_note_exists(ctx: ReviewContext, rule: Rule, params: NoteParams) -> list[Finding]:
    """A title-block field that says 'REF NOTE' has its note: a note that actually specifies the treatment."""
    pages = [p for p in ev.title_block_pages(ctx) if _REFERS_TO_NOTE.search(ev.value(p, params.field) or "")]
    if not pages:
        raise NotApplicable(f"the {params.field.replace('_', ' ')} field does not refer to a note")
    terms = [term(t) for t in HEAT_TREATMENT_TERMS]
    if any(any(t.search(n.text) for t in terms) for p in ctx.pages for n in _notes(p)):
        return []
    page = pages[0]
    name, value = params.field.replace("_", " "), ev.value(page, params.field)
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[ev.field(page, params.field)],
            comment=f"The {name} field says {value!r}, but no note on the drawing specifies the treatment.",
            recommended_correction="Add the note the field refers to, or state the treatment in the field.",
        )
    ]


class HardeningParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    needs_prior_hardening: list[str]
    hardening_terms: list[str]


@check("hardened_only_treatments_have_hardening", HardeningParams)
def hardened_only_treatments_have_hardening(
    ctx: ReviewContext, rule: Rule, params: HardeningParams
) -> list[Finding]:
    """Tempering or sub-zero treatment is only defined for hardened steel: the part must also be hardened."""
    needs = [term(t) for t in params.needs_prior_hardening]
    hardening = [term(t) for t in params.hardening_terms]
    texts: list[tuple[PageExtraction, TextItem | None, str]] = []
    for p in ctx.pages:
        texts += [(p, n, n.text) for n in _notes(p)]
        if v := ev.value(p, "heat_treatment"):
            texts.append((p, None, v))
    asking = [(p, n, t) for p, n, t in texts if any(x.search(t) for x in needs)]
    if not asking:
        raise NotApplicable("no tempering or sub-zero treatment specified")
    # "hardened and tempered" names its hardening in the same words, so a hardening term anywhere counts
    if any(h.search(t) for _, _, t in texts for h in hardening):
        return []
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[ev.text(p, n) if n else ev.field(p, "heat_treatment")],
            comment=f"{t.strip()!r} asks for a treatment that only follows hardening, but no hardening "
            "process is specified.",
            recommended_correction="Name the hardening process (e.g. hardened and tempered, toughened), or "
            "correct the treatment.",
        )
        for p, n, t in asking
    ]


def _table(ctx: ReviewContext, name: str, model: type) -> object:
    table = ctx.reference.get(name)
    if not isinstance(table, model):
        raise NotCheckable(f"reference table {name!r} not loaded (config/reference/{name}.yaml)")
    return table


def _materials(ctx: ReviewContext) -> Materials:
    table = _table(ctx, "materials", Materials)
    assert isinstance(table, Materials)
    return table


class TableParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str


@check("treatment_material_compat", TableParams)
def treatment_material_compat(ctx: ReviewContext, rule: Rule, params: TableParams) -> list[Finding]:
    """The surface treatment is one PARI's DES-12 allows on the material (e.g. anodizing: aluminium only).

    Treatments DES-12 does not list (painting, black oxide) and materials the table does not recognise are not
    compared; a steel whose grade is not stated is not compared either.
    """
    processes = _table(ctx, params.table, PlatingProcesses)
    assert isinstance(processes, PlatingProcesses)
    materials = _materials(ctx)
    out = []
    listed = compared = False
    for page in ev.title_block_pages(ctx):
        process = processes.identify(ev.value(page, "surface_treatment"))
        if process is None:
            continue
        listed = True
        material = ev.value(page, "material")
        cls = materials.classify(material)
        if cls is None or cls == "steel":
            continue
        compared = True
        if cls in process.materials:
            continue
        out.append(
            new_finding(
                rule,
                reviewer=REVIEWER,
                evidence=[ev.field(page, "surface_treatment"), ev.field(page, "material")],
                comment=f"{process.name} ({ev.value(page, 'surface_treatment')}) on {material} "
                f"({cls.replace('_', ' ')}): PARI's DES-12 allows it on "
                f"{', '.join(m.replace('_', ' ') for m in process.materials)} only.",
                recommended_correction="Use a treatment DES-12 lists for this material, or fix the material.",
            )
        )
    if not listed:
        raise NotApplicable("no DES-12 plating process in the surface treatment field")
    if not compared:
        raise NotCheckable("the material is not one the materials table recognises")
    return out


class NonMetalParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str
    non_metals: list[str] = []
    thermoplastic_softening_C: list[float] = []


def _heat_treatment(page: PageExtraction) -> list[EvidenceRef]:
    """Where this page specifies a heat treatment: the field itself, or the notes it refers to."""
    value = ev.value(page, "heat_treatment")
    if not value or ev.is_placeholder(value):
        return []
    if not _REFERS_TO_NOTE.search(value):
        return [ev.field(page, "heat_treatment")]
    terms = [term(t) for t in HEAT_TREATMENT_TERMS]
    return [ev.text(page, n) for n in _notes(page) if any(t.search(n.text) for t in terms)]


@check("heat_treatment_only_on_metals", NonMetalParams)
def heat_treatment_only_on_metals(ctx: ReviewContext, rule: Rule, params: NonMetalParams) -> list[Finding]:
    """A heat treatment (hardening, tempering, ...) is specified only for a metal part, never a plastic."""
    materials = _materials(ctx)
    extra = [re.compile(re.escape(n.split("(")[0].strip()), re.IGNORECASE) for n in params.non_metals]
    out = []
    specified = False
    for page in ev.title_block_pages(ctx):
        treatment = _heat_treatment(page)
        if not treatment:
            continue
        specified = True
        material = ev.value(page, "material")
        cls = materials.classify(material)
        plastic = materials.family(cls) == "non_metallic" or any(p.search(material or "") for p in extra)
        if cls is None and not plastic:
            raise NotCheckable("the material is not one the materials table recognises")
        if not plastic:
            continue
        out.append(
            new_finding(
                rule,
                reviewer=REVIEWER,
                evidence=[*treatment, ev.field(page, "material")],
                comment=f"A heat treatment ({treatment[0].quote!r}) is specified for a part in {material}, a "
                "non-metal: plastics are not heat treated.",
                recommended_correction="Remove the heat treatment, or correct the material.",
            )
        )
    if not specified:
        raise NotApplicable("no heat treatment specified")
    return out


_IZBP = re.compile(r"I\.?\s*Z\.?\s*B\.?\s*P|IRON\s+ZINC", re.IGNORECASE)


@check("izbp_trivalent")
def izbp_trivalent(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """Iron-zinc black passivation is called out as trivalent (PARI's DES-12 allows trivalent only)."""
    pages = [p for p in ev.title_block_pages(ctx) if _IZBP.search(ev.value(p, "surface_treatment") or "")]
    if not pages:
        raise NotApplicable("no IZBP surface treatment")
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[ev.field(page, "surface_treatment")],
            comment=f"The surface treatment {ev.value(page, 'surface_treatment')!r} does not say trivalent.",
            recommended_correction="Write I.Z.B.P. (TRIVALENT).",
        )
        for page in pages
        if "TRIVALENT" not in (ev.value(page, "surface_treatment") or "").upper()
    ]


_PAINT = re.compile(r"\b(PAINT(?:ING|ED)?|POWDER[\s-]*COAT(?:ING|ED)?|ENAMEL(?:LED)?|LACQUER(?:ED)?)\b", re.I)
# A colour code: RAL 7035, a Pantone or Munsell number, a British Standard colour. A colour name is not one.
_COLOUR_CODE = re.compile(r"\bRAL\s*\d{4}\b|\bPANTONE\b|\bMUNSELL\b|\bBS\s*(?:4800|381C?)\b", re.I)


@check("paint_colour_code")
def paint_colour_code(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """A painted or powder-coated part gives its colour by code (RAL 7035), not by a name or not at all."""
    out, painted = [], False
    for page in ev.title_block_pages(ctx):
        finish = ev.value(page, "surface_treatment") or ""
        if not _PAINT.search(finish):
            continue
        painted = True
        text = " ".join([finish, *(n.text for p in ctx.pages for n in [*p.notes, *p.body_text])])
        if not _COLOUR_CODE.search(text):
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[ev.field(page, "surface_treatment")],
                    comment=f"The finish is {finish!r} but no colour code (such as RAL 7035) is given.",
                    recommended_correction="State the colour by its code, e.g. RAL 7035.",
                )
            )
    if not painted:
        raise NotApplicable("the finish is not paint or powder coating")
    return out


# --- DES-11 heat treatment and DES-12 plating, read from the title block and the notes (_process) -----------


def _des11(ctx: ReviewContext, name: str) -> MaterialHeatTreatment:
    table = _table(ctx, name, MaterialHeatTreatment)
    assert isinstance(table, MaterialHeatTreatment)
    return table


def _plating_table(ctx: ReviewContext, name: str) -> PlatingProcesses:
    table = _table(ctx, name, PlatingProcesses)
    assert isinstance(table, PlatingProcesses)
    return table


def _treated(ctx: ReviewContext) -> list[pr.HeatTreatment]:
    found = pr.heat_treatments(ctx)
    if not found:
        raise NotApplicable("no heat treatment specified")
    return found


def _material(ctx: ReviewContext, table: MaterialHeatTreatment) -> pr.MaterialRows:
    rows = pr.des11_rows(ctx, table)
    if rows is None:
        raise NotCheckable("the material is not one of DES-11's rows (or is not stated)")
    return rows


def _process_name(process: str) -> str:
    return {"case": "case hardening", "through": "through hardening"}.get(process, process)


def _span(r: tuple[float, float], unit: str) -> str:
    return f"{r[0]:g}-{r[1]:g} {unit}" if r[0] != r[1] else f"{r[0]:g} {unit}"


@check("heat_treatment_allowed", TableParams)
def heat_treatment_allowed(ctx: ReviewContext, rule: Rule, params: TableParams) -> list[Finding]:
    """The heat treatment is one DES-11 tabulates for the material, not a NIL cell (e.g. EN9: no case
    hardening).

    When the material matches more than one DES-11 row, it fails only if every row prints NIL.
    """
    table = _des11(ctx, params.table)
    treated = _treated(ctx)
    material = _material(ctx, table)
    out, seen = [], set()
    for h in treated:
        if h.process in seen:
            continue
        seen.add(h.process)
        if all(row.treatments[h.process].status == "nil" for row in material.rows):
            keys = ", ".join(r.key for r in material.rows)
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[h.spec.evidence, material.evidence],
                    comment=f"{_process_name(h.process).capitalize()} ({h.spec.text.strip()!r}) on "
                    f"{material.text}: PARI's DES-11 prints NIL for it on {keys}.",
                    recommended_correction="Choose a treatment DES-11 tabulates for this material, or a "
                    "material that takes it (DES-11 note iii allows a justified exception, stated on the "
                    "drawing).",
                )
            )
    return out


@check("hardness_in_range", TableParams)
def hardness_in_range(ctx: ReviewContext, rule: Rule, params: TableParams) -> list[Finding]:
    """The hardness (and case depth) asked for lies inside DES-11's range for the material and process."""
    table = _des11(ctx, params.table)
    treated = [h for h in _treated(ctx) if h.hrc or h.depth_mm]
    if not treated:
        raise NotApplicable("no hardness or case depth stated")
    material = _material(ctx, table)
    out, seen = [], set()
    for h in treated:
        # a bare HARDENED names no process: any column DES-11 tabulates for the material may be the one meant
        columns: list[Process] = list(PROCESSES) if h.inferred else [h.process]
        cells = [
            (f"{r.key} {_process_name(col)}" if h.inferred else r.key, c)
            for r in material.rows
            for col in columns
            if (c := r.treatments[col]).status == "tabulated" and c.hardness
        ]
        if not cells or (h.process, h.hrc, h.depth_mm) in seen:
            continue  # a NIL cell is heat_treatment_allowed's finding
        seen.add((h.process, h.hrc, h.depth_mm))
        problems = []
        if h.hrc and not any(
            c.hardness and c.hardness.low <= h.hrc[0] and h.hrc[1] <= c.hardness.high for _, c in cells
        ):
            problems.append(
                f"hardness {_span(h.hrc, 'HRC')} against "
                + ", ".join(
                    f"{k} {_span((c.hardness.low, c.hardness.high), 'HRC')}" for k, c in cells if c.hardness
                )
            )
        depth_cells = [(k, c.depth_mm) for k, c in cells if c.depth_mm]
        if (
            h.depth_mm
            and depth_cells
            and not any(d.low <= h.depth_mm[0] and h.depth_mm[1] <= d.high for _, d in depth_cells)
        ):
            problems.append(
                f"depth {_span(h.depth_mm, 'mm')} against "
                + ", ".join(f"{k} {_span((d.low, d.high), 'mm')}" for k, d in depth_cells)
            )
        if problems:
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[h.spec.evidence, material.evidence],
                    comment=(
                        "Hardened (no process named)" if h.inferred else _process_name(h.process).capitalize()
                    )
                    + f" on {material.text}: "
                    + "; ".join(problems)
                    + " in PARI's DES-11.",
                    recommended_correction="Use DES-11's range for this material and process, or note why "
                    "not.",
                )
            )
    return out


@check("treatment_combination", TableParams)
def treatment_combination(ctx: ReviewContext, rule: Rule, params: TableParams) -> list[Finding]:
    """A nitrided part is not also chrome plated (DES-11: avoid chrome after nitriding).

    The other half of the rule, nitriding after finish machining, is about the process route and is left to
    the AI reviewers.
    """
    _des11(ctx, params.table)
    nitrided = [h for h in pr.heat_treatments(ctx) if h.process == "nitriding"]
    if not nitrided:
        raise NotApplicable("the part is not nitrided")
    chrome = [
        p for p in pr.platings(ctx, _plating_table(ctx, "plating_processes")) if "chrome" in p.process.id
    ]
    if not chrome:
        return []
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[nitrided[0].spec.evidence, chrome[0].spec.evidence],
            comment=f"The part is nitrided ({nitrided[0].spec.text.strip()!r}) and chrome plated "
            f"({chrome[0].spec.text.strip()!r}); PARI's DES-11 says to avoid chrome plating after nitriding.",
            recommended_correction="Drop one of the two treatments, or state why both are needed.",
        )
    ]


# Words that make a text a plating or coating call-out (what DES-12 lists), and finishes that are not one.
_PLATING_WORDS = re.compile(r"PLATING|PLATED|ANODI[SZ]|PASSIVAT|GALVANI[SZ]|COATING|COATED", re.I)


class ApprovedParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str
    not_plating: list[str] = []


@check("surface_treatment_approved", ApprovedParams)
def surface_treatment_approved(ctx: ReviewContext, rule: Rule, params: ApprovedParams) -> list[Finding]:
    """A plating or coating the drawing calls for is one of PARI's DES-12 processes.

    Finishes that are not plating (painting, powder coating, oil: `not_plating`) are not judged here.
    """
    table = _plating_table(ctx, params.table)
    other = [term(t) for t in params.not_plating]
    out, judged, seen = [], False, set()
    for s in pr.specs(ctx):
        from_field = s.evidence.kind == "title_block"
        if any(o.search(s.text) for o in other) or not (from_field or _PLATING_WORDS.search(s.text)):
            continue
        if s.evidence.kind == "title_block" and s.evidence.ref != "surface_treatment":
            continue
        normal = re.sub(r"[^A-Z]", "", s.text.upper())
        if normal in {"NA", "NIL", "NONE"} or ev.is_placeholder(s.text):
            continue
        judged = True
        if table.identify(s.text) is None and (s.page.page_number, normal) not in seen:
            seen.add((s.page.page_number, normal))
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[s.evidence],
                    comment=f"{s.text.strip()!r} is not one of the plating processes in PARI's DES-12.",
                    recommended_correction="Use a DES-12 process, or get the treatment approved and name it "
                    "as "
                    "DES-12 does.",
                )
            )
    if not judged:
        raise NotApplicable("no plating or coating called for")
    return out


class PrerequisiteParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str
    prerequisites: str


@check("treatment_prerequisites", PrerequisiteParams)
def treatment_prerequisites(ctx: ReviewContext, rule: Rule, params: PrerequisiteParams) -> list[Finding]:
    """A plating's DES-12 prerequisites are met: hard chrome needs a case or through hardened base of at least
    45 HRC, QPQ is not put on a case hardened part, Balzer coating needs over 55 HRC and never EN24."""
    table = _plating_table(ctx, params.table)
    prereq = _table(ctx, params.prerequisites, Prerequisites)
    assert isinstance(prereq, Prerequisites)
    rows = {r.process: r for r in prereq.rows}
    plated = [p for p in pr.platings(ctx, table) if p.process.id in rows]
    if not plated:
        raise NotApplicable("no plating with DES-12 prerequisites (hard chrome, QPQ, Balzer)")
    heat = pr.heat_treatments(ctx)
    processes = {h.process for h in heat}
    material = pr.des11_rows(ctx, _des11(ctx, "material_heat_treatment"))
    out, seen = [], set()
    for p in plated:
        if p.process.id in seen:
            continue
        seen.add(p.process.id)
        row = rows[p.process.id]
        problems = []
        if row.required_heat_one_of and not processes & set(row.required_heat_one_of):
            problems.append(
                f"it needs a {' or '.join(row.required_heat_one_of)} hardened base, and none is specified"
            )
        for limit in row.hardness_limits:
            for h in heat:
                if h.hrc is None or h.process not in {"through", "case", "toughening"}:
                    continue
                low = h.hrc[0]
                if (limit.operator == ">=" and low < limit.hrc) or (
                    limit.operator == ">" and low <= limit.hrc
                ):
                    problems.append(
                        f"the base is {_span(h.hrc, 'HRC')}, and it needs {limit.operator} {limit.hrc:g} HRC"
                    )
                    break
        for bad in [*row.forbidden_heat, *row.not_recommended_heat]:
            if bad in processes:
                problems.append(f"DES-12 does not recommend it on a {_process_name(bad)} part")
        if material and (keys := {r.key for r in material.rows} & set(row.forbidden_material)):
            problems.append(f"DES-12 says not to use it on {', '.join(sorted(keys))}")
        if problems:
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[p.spec.evidence, *([heat[0].spec.evidence] if heat else [])],
                    comment=f"{p.process.name} ({p.spec.text.strip()!r}): " + "; ".join(problems) + ".",
                    recommended_correction="Specify the base treatment DES-12 asks for, or a different "
                    "plating.",
                )
            )
    return out


_CHAMFER = re.compile(r"\d+(?:\.\d+)?\s*[xX×]\s*45\s*°?|CHAMFER", re.I)


class EdgeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    processes: list[str]


@check("plating_edge_radius", EdgeParams)
def plating_edge_radius(ctx: ReviewContext, rule: Rule, params: EdgeParams) -> list[Finding]:
    """Hard chrome, flash chrome and QPQ parts have their edges broken by a radius: a chamfer is flagged."""
    names = [n.lower() for n in params.processes]
    plated = [
        p
        for p in pr.platings(ctx, _plating_table(ctx, "plating_processes"))
        if any(n in p.process.name.lower() for n in names)
    ]
    if not plated:
        raise NotApplicable(f"no {', '.join(params.processes)} on the part")
    chamfers = [
        (pg, d) for pg in ctx.pages for d in [*pg.dimensions, *pg.other_numeric] if _CHAMFER.search(d.text)
    ]
    if not chamfers:
        return []
    shown = chamfers[:5]
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[plated[0].spec.evidence, *(ev.text(pg, d) for pg, d in shown)],
            comment=f"The part has {plated[0].process.name} and {len(chamfers)} chamfer call-out(s) "
            f"({', '.join(repr(d.text) for _, d in shown)}); plated edges should be blended by a radius.",
            recommended_correction="Replace the chamfers on plated edges with a radius, or note why a "
            "chamfer is "
            "acceptable.",
        )
    ]


_MASK = re.compile(r"MASK", re.I)


class MaskingParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str
    processes: list[str]  # DES-12 process ids thick or hard enough to spoil a thread


@check("masking_note", MaskingParams)
def masking_note(ctx: ReviewContext, rule: Rule, params: MaskingParams) -> list[Finding]:
    """A part with a thick or hard plating and threads says which surfaces to mask (threads, mating faces).

    Thin finishes such as IZBP are not judged: PARI's drawings leave their threads unmasked.
    """
    plated = [
        p for p in pr.platings(ctx, _plating_table(ctx, params.table)) if p.process.id in params.processes
    ]
    if not plated:
        raise NotApplicable("no thick or hard plating on the part")
    found = threads(ctx)
    if not found:
        raise NotApplicable("the plated part has no threads")
    if any(_MASK.search(s.text) for s in pr.specs(ctx)):
        return []
    t = found[0]
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[plated[0].spec.evidence, ev.text(t.page, t.item)],
            comment=f"The part has {plated[0].process.name} and {len(found)} thread call-out(s) "
            f"(e.g. {t.text}), "
            "but no note says which surfaces to mask.",
            recommended_correction="Add a masking note for the threads and mating faces, e.g. 'MASK ALL "
            "THREADS "
            "DURING PLATING', or state that plating them is acceptable.",
        )
    ]
