"""The answer check (ADR 0011): every citation resolves, and every number comes from the data.

An answer cites inline: `[D12]`, `[p2:S3]`, `[L7]`, `[N2]`, `[F4]`, `[TB:material]`, `[R:WST-207]`,
`[T:is919_fits H7 20]` (several may share brackets: `[D12, D13]`). A number in the answer must appear in what
the agent was shown in this conversation (the overview, tool results, the engineer's own words): the tools do
the arithmetic, the model only quotes. Small counts and ordinals (0 to 10) are exempt.
"""

from __future__ import annotations

import re

from drawing_intelligence.qa.data import DrawingData

_MARKER = re.compile(r"\[([^\[\]\n]{1,80})\]")
# something meant as a citation but not in a valid form: "[L:C10]", "[L?]", "[D 12]"
_CITE_ATTEMPT = re.compile(r"^(?:p\d+:)?(?:TB|[DSLNFRT])(?:\s|[:?\d])")
_CITE_FORM = re.compile(r"^(?:p\d+:)?(?:[DSLN]\d+|TB:\w+)$|^F\d+$|^R:[A-Z]+-\d+$|^T:.+$")
_UNITS = re.compile(r"(\d)\s*(?:mm|µm|um|°|deg\b)", re.IGNORECASE)
# a number not glued to an ID: "H7", "M8", "WST-207", "C4", "6H" are not numbers to check
_NUMBER = re.compile(r"(?<![\w.])(?<!\w-)([+\-−±]?)(\d+(?:\.\d+)?)(?![\w.]*[A-Za-z])(?!\.\d)")
_ANY_NUMBER = re.compile(r"([+\-−]?)(\d+(?:\.\d+)?)")
EXEMPT_INTEGERS = range(11)
NOT_IN_DATA = "not in the drawing's data"  # the fixed phrase of an absence answer (system prompt)


def citations(text: str) -> list[str]:
    out = []
    for m in _MARKER.finditer(text):
        out += [c.strip() for c in m.group(1).split(",") if c.strip()]
    return out


def _signed(sign: str, digits: str) -> float:
    v = float(digits)
    return -v if sign in ("-", "−") else v


class Corpus:
    """Every number the agent has been shown, signed as printed (an unsigned number counts as positive)."""

    def __init__(self) -> None:
        self.signed: set[float] = set()
        self.unsigned: set[float] = set()

    def add(self, text: str) -> None:
        for sign, digits in _ANY_NUMBER.findall(text):
            v = _signed(sign, digits)
            self.signed.add(round(v, 6))
            self.unsigned.add(round(abs(v), 6))

    def has(self, sign: str, digits: str) -> bool:
        v = round(_signed(sign, digits), 6)
        if sign in ("", "±"):
            return abs(v) in self.unsigned
        return v in self.signed


def check_answer(text: str, data: DrawingData, lookups: set[str], corpus: Corpus) -> list[str]:
    """The problems with an answer; an empty list means it is verified."""
    problems = []
    cites = citations(text)
    for c in cites:
        if not _CITE_FORM.match(c):
            if _CITE_ATTEMPT.match(c):
                problems.append(f"[{c}] is not a valid citation: use an ID exactly as a tool printed it")
            continue  # brackets used as ordinary text, e.g. "[optional]"
        if c.startswith("F"):
            ok = int(c[1:]) in data.findings
        elif c.startswith("R:"):
            ok = data.rule(c[2:]) is not None
        elif c.startswith("T:"):
            ok = c in lookups
        else:
            ok = c in data.items
        if not ok:
            hint = (
                "made by a lookup_standard call in this conversation"
                if c.startswith("T:")
                else "on this drawing"
            )
            problems.append(f"citation [{c}] is not {hint}")
    bare = _MARKER.sub(" ", text)
    bare = _UNITS.sub(r"\1 ", bare)
    unknown = []
    for m in _NUMBER.finditer(bare):
        sign, digits = m.group(1), m.group(2)
        if not sign and "." not in digits and int(digits) in EXEMPT_INTEGERS:
            continue
        if not corpus.has(sign, digits):
            unknown.append(f"{sign}{digits}")
    if unknown:
        problems.append(
            f"number(s) {', '.join(dict.fromkeys(unknown))} are in no tool result and not in the overview: "
            "quote values exactly as a tool returned them, or call a tool that gives them"
        )
    has_values = any(
        not (not m.group(1) and "." not in m.group(2) and int(m.group(2)) in EXEMPT_INTEGERS)
        for m in _NUMBER.finditer(bare)
    )
    if has_values and not any(_CITE_FORM.match(c) for c in cites):
        problems.append("the answer states values but cites nothing: add the [ID] each value comes from")
    return problems
