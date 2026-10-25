"""What a check function reads: one drawing's stage 1 and stage 2 results, plus the rulebook (ADR 0010)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from drawing_intelligence.extraction.template import Template
from drawing_intelligence.review.rulebook import DrawingType, PartFamily, Rulebook
from drawing_intelligence.schemas import DrawingKnowledge, Extraction, PageExtraction


@dataclass(frozen=True)
class ReviewContext:
    """Read-only input of every check. Checks loop over the pages themselves.

    `knowledge` maps a page number to its `DrawingKnowledge`, or None when understanding did not run or its
    output was invalid; a check that needs it raises `NotCheckable`.
    """

    extraction: Extraction
    rulebook: Rulebook
    template: Template
    knowledge: Mapping[int, DrawingKnowledge | None] = field(default_factory=dict)
    reference: Mapping[str, Any] = field(default_factory=dict)  # lookup tables (config/reference), later
    part_family: PartFamily | None = None
    drawing_type: DrawingType | None = None

    @property
    def pages(self) -> list[PageExtraction]:
        return self.extraction.pages

    def knowledge_of(self, page: PageExtraction) -> DrawingKnowledge | None:
        return self.knowledge.get(page.page_number)

    def parse_date(self, text: str | None) -> date | None:
        """A title-block date in the template's format (PARI: day/month/year); None if it doesn't parse."""
        if not text:
            return None
        sep = next((c for c in "/-." if c in self.template.date_format), "/")
        normal = re.sub(r"[/\-.]", sep, text.strip())  # 06-05-2024 and 06.05.2024 are 06/05/2024
        try:
            return datetime.strptime(normal, self.template.date_format).date()
        except ValueError:
            return None
