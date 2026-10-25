"""Surface finish, coating and heat-treatment checks on the title block and the notes (exact text)."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from drawing_intelligence.review.checks import _evidence as ev
from drawing_intelligence.review.checks._registry import NotApplicable, NotCheckable, check
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.reference import Materials, PlatingProcesses
from drawing_intelligence.review.rulebook import Rule, new_finding
from drawing_intelligence.schemas import EvidenceRef, Finding, PageExtraction, TextItem

REVIEWER = "checks"
_REFERS_TO_NOTE = re.compile(r"NOTE", re.IGNORECASE)  # REF NOTE, REFER NOTE, REF.NOTE; not REF. DRG / REF BOM
# Words that make a note a heat-treatment specification, not just its heading.
HEAT_TREATMENT_TERMS = (
    "harden", "tough", "temper", "anneal", "normali", "carburi", "nitrid", "case", "induction", "flame",
    "quench", "stress reliev", "HRC", "HRB", "HB", "HV",
)  # fmt: skip


def _term(term: str) -> re.Pattern[str]:
    """A rulebook term as a word-start pattern: 'tempering' matches TEMPERED, 'carburizing' CARBURISED."""
    stem = re.sub(r"(ing|ed|e)$", "", term.strip().lower())
    stem = re.escape(stem).replace("z", "[sz]").replace(r"\-", r"[\s-]?").replace(r"\ ", r"\s+")
    return re.compile(r"(?<![a-z])" + stem, re.IGNORECASE)


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
    terms = [_term(t) for t in HEAT_TREATMENT_TERMS]
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
    needs = [_term(t) for t in params.needs_prior_hardening]
    hardening = [_term(t) for t in params.hardening_terms]
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
    terms = [_term(t) for t in HEAT_TREATMENT_TERMS]
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
