"""What the web demo shows of a session, built from the saved results. Nothing here judges a drawing."""

from __future__ import annotations

import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from drawing_intelligence.api.runs import DemoSession
from drawing_intelligence.qa.agent import Answer
from drawing_intelligence.qa.data import DrawingData, note_bbox
from drawing_intelligence.report.build import location, numbered
from drawing_intelligence.report.zones import zone
from drawing_intelligence.schemas import PageExtraction
from drawing_intelligence.schemas.review import CATEGORY_LABELS
from drawing_intelligence.viz.annotate import full_sheet

SHEET_WIDTH = 2400  # px of the sheet image sent to the browser
_CITE = re.compile(r"\[([^\[\]\n]{1,80})\]")


@lru_cache
def plain_english(config_dir: Path) -> dict[str, dict[str, str]]:
    p = config_dir / "demo" / "plain_english.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    return {"by_rule": data.get("by_rule") or {}, "by_category": data.get("by_category") or {}}


def sheet_image(sess: DemoSession, page: PageExtraction) -> Path:
    """The sheet as a PNG the browser can show; records its size and the PDF-points-to-pixels factor."""
    assert page.images is not None
    out = sess.folder / f"sheet_{page.page_number}.png"
    if page.page_number not in sess.sheets or not out.exists():
        src = full_sheet(sess.out_dir, page)
        s = SHEET_WIDTH / src.width
        img = src.resize((SHEET_WIDTH, round(src.height * s)))
        img.save(out, optimize=True)
        sess.sheets[page.page_number] = (page.images.dpi / 72 * s, img.width, img.height)
    return out


def _px(bbox: list[float] | None, k: float) -> list[float] | None:
    return [round(v * k, 1) for v in bbox] if bbox else None


def session_summary(sess: DemoSession) -> dict[str, Any]:
    return {
        "id": sess.id,
        "name": sess.name,
        "demo_id": sess.demo_id,
        "live": sess.live,
        "status": sess.status,
        "error": sess.error,
        "stages": [
            {"key": st.key, "label": st.label, "status": st.status, "seconds": st.seconds}
            for st in sess.stages
        ],
        "seconds": round((sess.finished or 0) - sess.started, 1) if sess.started and sess.finished else None,
    }


def session_detail(sess: DemoSession, config_dir: Path) -> dict[str, Any]:
    out = session_summary(sess)
    res, data = sess.result, sess.data
    if res is None or data is None or res.review is None:
        return out
    review = res.review
    pages = data.pages
    sheets = []
    for n, page in pages.items():
        if page.images is None:
            continue
        sheet_image(sess, page)
        _, w, h = sess.sheets[n]
        sheets.append({"page": n, "url": f"/api/sessions/{sess.id}/sheets/{n}.png", "w": w, "h": h})
    factors = {n: v[0] for n, v in sess.sheets.items()}
    words = plain_english(config_dir)
    findings = []
    for nf in numbered(review):
        f = nf.finding
        rule = data.rule(f.rule_id) if f.rule_id else None
        ev = []
        for e in f.evidence:
            page = pages.get(e.page)
            bbox = e.bbox
            if bbox is None and e.kind == "note" and page is not None:  # place the note from stage 1's text
                bbox = note_bbox(page, e.quote or "")
            ev.append(
                {
                    "page": e.page,
                    "ref": e.ref,
                    "quote": e.quote,
                    "kind": e.kind,
                    "bbox": _px(bbox, factors.get(e.page, 0)),
                    "zone": zone(page, data.template, bbox) if page and bbox else None,
                }
            )
        fb = sess.feedback.get(f.id)
        findings.append(
            {
                "no": nf.no,
                "id": f.id,
                "rule_id": f.rule_id,
                "requirement": f.requirement,
                "rule_source": (f"{rule.source.document}" if rule else None),
                "category": f.category,
                "category_label": CATEGORY_LABELS.get(f.category, f.category),
                "result": f.result,
                "severity": f.severity,
                "source": f.source,
                "reviewer": f.reviewer,
                "comment": f.comment,
                "recommended_correction": f.recommended_correction,
                "location": location(f, res.extraction, data.template),
                "evidence": ev,
                "plain_english": words["by_rule"].get(f.rule_id or "")
                or words["by_category"].get(f.category),
                "feedback": fb.decision if fb else None,
            }
        )
    statuses = Counter(s.status for s in review.rule_statuses)
    tb = res.extraction.pages[0].title_block_fields if res.extraction.pages else {}
    out.update(
        {
            "title_block": {k: v.value for k, v in tb.items() if v.value},
            "sheets": sheets,
            "findings": findings,
            "rejected": len(res.rejected),
            "coverage": {
                k: statuses.get(k, 0) for k in ("fail", "warning", "pass", "not_checked", "not_applicable")
            },
            "rules_total": len(review.rule_statuses),
            "reviewers_run": review.reviewers_run,
            "cost_usd": round(sess.billed(), 4),
            "qa_cost_usd": round(sess.qa_cost, 4),
            "cached": sess.cached(),
            "model": res.understanding[0].model if res.understanding else None,
            "rulebook_version": review.rulebook_version,
        }
    )
    return out


def answer_view(answer: Answer, data: DrawingData, sess: DemoSession) -> dict[str, Any]:
    """The answer plus where each cited item sits on the sheet, so the UI can highlight it."""
    cites = []
    factors = {n: v[0] for n, v in sess.sheets.items()}
    for m in dict.fromkeys(_CITE.findall(answer.text)):
        c = m.strip()
        if re.fullmatch(r"F\d+", c):
            cites.append({"cite": c, "finding_no": int(c[1:])})
        elif c in data.items:
            it = data.items[c]
            cites.append(
                {"cite": c, "page": it.page, "bbox": _px(it.bbox, factors.get(it.page, 0)), "text": it.text}
            )
    return {
        "text": answer.text,
        "verified": answer.verified,
        "problems": answer.problems,
        "cost_usd": round(answer.cost_usd, 4),
        "stopped_by": answer.stopped_by,
        "cites": cites,
    }
