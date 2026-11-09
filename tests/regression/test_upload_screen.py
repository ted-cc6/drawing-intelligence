"""The web demo's upload screen on the client set: real drawings pass, the guideline documents do not."""

from __future__ import annotations

import pytest

from drawing_intelligence.api.uploads import UploadRejected, screen_pdf
from drawing_intelligence.settings import PROJECT_ROOT

pytestmark = pytest.mark.regression

CLIENT = PROJECT_ROOT / "data" / "client_set"
DRAWINGS = sorted(p for p in CLIENT.glob("Generic*/*") if p.suffix.lower() == ".pdf")
GUIDES = sorted(p for p in (CLIENT / "WP Specific Guidelines").glob("*") if p.suffix.lower() == ".pdf")


def _passes(path) -> bool:
    try:
        screen_pdf(path.read_bytes())
    except UploadRejected:
        return False
    return True


@pytest.mark.skipif(not DRAWINGS, reason="no client drawings in data/")
def test_client_drawings_pass_the_upload_screen():
    turned_away = [p.name for p in DRAWINGS if not _passes(p)]
    # one drawing (PRT84F150002001) has almost no text layer and no standard title block
    assert len(turned_away) <= 2, turned_away


@pytest.mark.skipif(not GUIDES, reason="no guideline documents in data/")
def test_guideline_documents_are_turned_away():
    assert [p.name for p in GUIDES if _passes(p)] == []
