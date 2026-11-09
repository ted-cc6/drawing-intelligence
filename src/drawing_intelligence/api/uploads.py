"""Checks on an uploaded PDF before a live review spends anything: it opens, is short, is a PARI drawing.

All free and fast (no model call), so a wrong file is turned away in a second with a sentence the user can act
on, and it does not use up one of the demo's live reviews.

"Looks like a PARI drawing" is the standard title block found by its anchors (as in stage 1) or, for the older
variant title blocks, the words "scale" and "material" in the text layer. On the repo's 1,203 client PDFs this
accepts 1,202 drawings and turns away all four guideline documents.
"""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from drawing_intelligence.extraction.template import load_template
from drawing_intelligence.extraction.title_block import layout, page_words

MAX_PAGES = 4  # client drawings have 1-3 sheets; more is a document, and a long live run on the demo's CPU
MIN_TEXT_CHARS = 50


class UploadRejected(Exception):
    """An upload the demo will not review; `message` is shown to the user as it is."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def screen_pdf(data: bytes, config_dir: Path | None = None) -> None:
    """Raise `UploadRejected` unless `data` is a PDF drawing the live review can handle."""
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:
        raise UploadRejected(415, "This file could not be opened as a PDF. It may be damaged.") from e
    with doc:
        if doc.needs_pass:
            raise UploadRejected(422, "This PDF is password-protected. Upload a copy without a password.")
        if doc.page_count == 0:
            raise UploadRejected(422, "This PDF has no pages.")
        if doc.page_count > MAX_PAGES:
            raise UploadRejected(
                422,
                f"This PDF has {doc.page_count} pages. "
                f"The demo reviews drawings of up to {MAX_PAGES} sheets.",
            )
        text = " ".join(str(page.get_text("text")) for page in doc)
        if len(text.strip()) < MIN_TEXT_CHARS:
            raise UploadRejected(
                422,
                "This PDF has no readable text (it may be a scan or an image). The review reads the "
                "drawing's text, so upload the PDF exported from Solid Edge.",
            )
        template = load_template(config_dir=config_dir)
        standard = any(
            layout(page_words(p), template, p.rect.width, p.rect.height) == "standard" for p in doc
        )
        lower = text.lower()
        if not standard and not (re.search(r"\bscale\b", lower) and re.search(r"\bmat(eria)?l\b", lower)):
            raise UploadRejected(
                422,
                "This does not look like a PARI drawing: no title block was found. Upload a drawing made on "
                "the Wipro PARI Solid Edge template.",
            )
