"""Compare revisions: which findings are new, fixed or still open between two reviews, and what changed in the
title block and the revision table.

Works on the session views the UI already gets (`views.session_detail`). Findings are matched on their rule
and an anchor on the sheet. Dimension and symbol refs (D12, S3) are positions in the page's list, so adding
one dimension renumbers the rest: for those the anchor is the quoted text without its tolerance, plus its
zone. Known limit: a dimension whose nominal value changed shows as one fixed finding and one new one.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

_NUMBERED = re.compile(r"[DS]\d+")
_TOLERANCE = re.compile(r"\s*(\([^()]*\)\s*$|±.*$)")


def anchor(f: dict[str, Any]) -> str:
    """The key a finding is matched on across two reviews."""
    key = f.get("rule_id") or f.get("category") or ""
    ev = next((e for e in f.get("evidence") or [] if e.get("ref") or e.get("quote")), None)
    if ev is None:
        return f"{key}|{f.get('location') or ''}"
    ref = ev.get("ref")
    if ref and not _NUMBERED.fullmatch(ref):
        return f"{key}|{ref}"
    nominal = " ".join(_TOLERANCE.sub("", ev.get("quote") or "").split())
    return f"{key}|{nominal}|{ev.get('zone') or ''}"


def _quote(f: dict[str, Any]) -> str | None:
    return next((e["quote"] for e in f.get("evidence") or [] if e.get("quote")), None)


def _side(v: dict[str, Any]) -> dict[str, Any]:
    tb = v.get("title_block") or {}
    return {
        "id": v.get("id"),
        "name": v.get("name"),
        "number": tb.get("number"),
        "revision": tb.get("revision"),
    }


def compare(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """The differences between two session views, old first."""
    waiting: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in old.get("findings") or []:
        waiting[anchor(f)].append(f)
    added, still_open = [], []
    for f in new.get("findings") or []:
        match = waiting[anchor(f)]
        if not match:
            added.append(f)
            continue
        was, now = _quote(match.pop(0)), _quote(f)
        changed = was != now
        still_open.append({**f, "was": was if changed else None, "now": now if changed else None})
    fixed = [f for fs in waiting.values() for f in fs]

    tb_old, tb_new = old.get("title_block") or {}, new.get("title_block") or {}
    title_block = [
        {"field": k, "old": tb_old.get(k), "new": tb_new.get(k)}
        for k in sorted(tb_old.keys() | tb_new.keys())
        if tb_old.get(k) != tb_new.get(k)
    ]
    rows_old, rows_new = old.get("revision_rows") or [], new.get("revision_rows") or []

    a, b = _side(old), _side(new)
    notes = []
    if a["number"] != b["number"]:
        notes.append(
            f"These are different drawings: {a['number'] or 'no number'} and {b['number'] or 'no number'}."
        )
    elif (added or fixed) and a["revision"] == b["revision"]:
        notes.append(
            f"Both sheets say revision {a['revision']}. The findings changed, so the drawing changed without"
            " a new revision."
        )
    return {
        "old": a,
        "new": b,
        "findings": {"new": added, "fixed": fixed, "still_open": still_open},
        "title_block": title_block,
        "revision_rows": {
            "added": [r for r in rows_new if r not in rows_old],
            "removed": [r for r in rows_old if r not in rows_new],
        },
        "notes": notes,
    }
