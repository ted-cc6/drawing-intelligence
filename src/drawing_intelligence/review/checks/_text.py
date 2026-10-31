"""Text helpers shared by the check modules: term patterns, numbered note lists, template notes."""

from __future__ import annotations

import re

from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.schemas import PageExtraction, TextLine


def term(word: str) -> re.Pattern[str]:
    """A rulebook term as a word-start pattern: 'tempering' matches TEMPERED, 'carburizing' CARBURISED."""
    stem = re.sub(r"(ing|ed|e)$", "", word.strip().lower())
    stem = re.escape(stem).replace("z", "[sz]").replace(r"\-", r"[\s-]?").replace(r"\ ", r"\s+")
    return re.compile(r"(?<![a-z])" + stem, re.IGNORECASE)


# A numbered note: "1) TO BE HARDENED". Also "1) # USE STD. BAR" (PARI's # and $ mark material or finish
# notes), a first note on the heading line ("NOTE:- 1) TO BE TOUGHENED") and the French copy ("1) À").
# PARI's template notes are numbered "1.ALL DIMENSIONS ARE ..." and are skipped (they are on every sheet), as
# is a decimal like "1.2 H13" (a digit, not a letter, follows the point).
NUMBERED = re.compile(r"^\s*(?:NOTES?\s*[:.\-]*\s*)?(\d{1,2})\s*[.)]\s*(?=[#$]?\s*[^\W\d_]|\()")
# The template's three numbered notes; "IF IN DOUBT ," is printed on its own line, apart from "ASK TEAM
# MEMBER", which the template's boilerplate patterns (they match the whole sentence) do not recognise.
TEMPLATE_NUMBERED = re.compile(r"\s*(ALL\s+DIMENSIONS|DO\s+NOT\s+SCALE|IF\s+IN\s+DOUBT)", re.IGNORECASE)
ACCENTED = re.compile(r"^\s*(?:NOTES?\s*[:.\-]*\s*)?\d{1,2}\s*[.)]\s*[#$]?\s*[À-ÖØ-Þ]")
COLUMN_TOLERANCE = 4.0  # pts: lines of one list start at the same x


def numbered_lists(ctx: ReviewContext, page: PageExtraction) -> list[list[tuple[int, TextLine]]]:
    """The page's numbered note lists, each in printed order.

    A list is a run of numbered lines in one column (same left edge), top to bottom; a number 1 starts a new
    list, so an English list with its French copy below it makes two.
    """
    lines = []
    for ln in page.body_text:
        m = NUMBERED.match(ln.text)
        rest = ln.text[m.end() :] if m else ""
        if m and not TEMPLATE_NUMBERED.match(rest) and not ctx.template.is_boilerplate(rest):
            lines.append((int(m.group(1)), ln))
    columns: list[list[tuple[int, TextLine]]] = []
    for n, ln in sorted(lines, key=lambda t: t[1].bbox[0]):
        if columns and ln.bbox[0] - columns[-1][-1][1].bbox[0] <= COLUMN_TOLERANCE:
            columns[-1].append((n, ln))
        else:
            columns.append([(n, ln)])
    lists: list[list[tuple[int, TextLine]]] = []
    for column in columns:
        current: list[tuple[int, TextLine]] | None = None
        for n, ln in sorted(column, key=lambda t: t[1].bbox[1]):
            # a 1 starts a copy (the French list) only after a full list or on an accented line; a lone
            # "1)" after a single note is a repeat
            if current is None or (n == 1 and (len(current) >= 2 or ACCENTED.match(ln.text))):
                current = []
                lists.append(current)
            current.append((n, ln))
    return lists


def template_note(page: PageExtraction) -> TextLine | None:
    """The page's first line of the template's general notes ("1.ALL DIMENSIONS ARE", "2.DO NOT SCALE")."""
    for ln in page.body_text:
        m = NUMBERED.match(ln.text)
        if TEMPLATE_NUMBERED.match(ln.text[m.end() :] if m else ln.text):
            return ln
    return None
