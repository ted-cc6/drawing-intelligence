"""Score the model's symbols against the answer key: correct, phantom, missed - per type and thinking setting.

Two matching rules, both reported:
- location: a model symbol matches an unused answer-key symbol of the same type on the same page whose bbox
  centre is within MATCH_PT points (model bboxes are approximate). Unmatched model symbols are phantoms,
  unmatched key symbols are misses.
- count: per page and type, correct = min(model count, key count). Ignores where the symbol is, so it is the
  lenient upper bound.
Model symbols inside the template regions (title block, tolerance table, borders) are reported separately as
`template`: they are real marks (e.g. the "VV" in the MACHINING field) but not drawing symbols.

Writes results/scores.csv and results/per_page.csv.

Run:
    python spikes/spike_d_symbols/score.py
"""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict

import pymupdf
from common import DRAWINGS, OUT, RESULTS, SYMBOL_TYPES

from drawing_intelligence.extraction.template import load_template

MATCH_PT = 60.0
TYPES = (*SYMBOL_TYPES, "other")

# How the model may write each GD&T characteristic (glyph or word) -> the answer key's name.
CHARACTERISTICS = {
    "flatness": ("▱", "⏥", "flat"),
    "straightness": ("—", "⏤", "straight"),
    "perpendicularity": ("⊥", "perpend"),
    "parallelism": ("∥", "//", "parallel"),
    "concentricity": ("◎", "concentric"),
    "symmetry": ("⌯", "≡", "symmetr"),
    "circular_runout": ("↗", "circular run"),
    "total_runout": ("⌰", "total run"),
    "position": ("⌖", "⊕", "position"),
    "profile_of_line": ("⌒", "profile"),
    "cylindricity": ("⌭", "cylindric"),
}


def characteristic(value: str | None) -> str | None:
    v = (value or "").lower()
    for name, marks in CHARACTERISTICS.items():
        if any(m in v for m in marks):
            return name
    return None


def _centre(b: list[float]) -> tuple[float, float]:
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def _inside(b: list[float] | None, regions) -> bool:
    if not b:
        return False
    x, y = _centre(b)
    return any(r[0] <= x <= r[2] and r[1] <= y <= r[3] for r in regions)


def main() -> None:
    key = json.loads((RESULTS / "answer_key.json").read_text(encoding="utf-8"))
    template = load_template()
    totals: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    per_page = []
    for setting in ("off", "on"):
        for name, pdf in DRAWINGS.items():
            with pymupdf.open(pdf) as doc:
                sizes = [(p.rect.width, p.rect.height) for p in doc]
            for n, (w, h) in enumerate(sizes, 1):
                f = OUT / "runs" / name / f"page_{n}_{setting}.json"
                if not f.exists():
                    continue
                run = json.loads(f.read_text(encoding="utf-8"))
                t = totals[(setting, "_pages")]
                t["pages"] += 1
                t["cost_usd"] += run["cost_usd"]
                t["latency_s"] += run["latency_s"]
                t["output_tokens"] += run["output_tokens"]
                model = (run["knowledge"] or {}).get("symbols", [])
                regions = template.excluded_rects(w, h)
                truth = key[name][str(n)]
                for typ in TYPES:
                    pred = [s for s in model if s["type"] == typ]
                    in_template = [s for s in pred if _inside(s.get("bbox"), regions)]
                    pred = [s for s in pred if s not in in_template]
                    gold = [s for s in truth if s["type"] == typ]
                    used: set[int] = set()
                    correct = right_char = 0
                    for s in pred:
                        if not s.get("bbox"):
                            continue
                        cx, cy = _centre(s["bbox"])
                        best = min(
                            (
                                (math.dist((cx, cy), _centre(g["bbox"])), i)
                                for i, g in enumerate(gold)
                                if i not in used
                            ),
                            default=None,
                        )
                        if best and best[0] <= MATCH_PT:
                            used.add(best[1])
                            correct += 1
                            truth_char = gold[best[1]]["value"].split()[0]
                            right_char += characteristic(s.get("value")) == truth_char
                    row = {
                        "setting": setting,
                        "drawing": name,
                        "page": n,
                        "type": typ,
                        "key": len(gold),
                        "model": len(pred),
                        "template": len(in_template),
                        "correct_loc": correct,
                        "phantom_loc": len(pred) - correct,
                        "missed_loc": len(gold) - correct,
                        "correct_count": min(len(pred), len(gold)),
                        "gdt_char_right": right_char if typ == "gdt" else 0,
                    }
                    per_page.append(row)
                    agg = totals[(setting, typ)]
                    for k in (
                        "key",
                        "model",
                        "template",
                        "correct_loc",
                        "phantom_loc",
                        "missed_loc",
                        "correct_count",
                        "gdt_char_right",
                    ):
                        agg[k] += row[k]
    with (RESULTS / "per_page.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=per_page[0].keys())
        w.writeheader()
        w.writerows(per_page)
    rows = []
    for (setting, typ), a in sorted(totals.items()):
        if typ == "_pages":
            continue
        model, keyn = a["model"], a["key"]
        rows.append(
            {
                "setting": setting,
                "type": typ,
                "key": int(keyn),
                "model": int(model),
                "template": int(a["template"]),
                "correct_loc": int(a["correct_loc"]),
                "phantom_loc": int(a["phantom_loc"]),
                "missed_loc": int(a["missed_loc"]),
                "phantom_rate_loc": round(a["phantom_loc"] / model, 3) if model else None,
                "miss_rate_loc": round(a["missed_loc"] / keyn, 3) if keyn else None,
                "miss_rate_count": round(1 - a["correct_count"] / keyn, 3) if keyn else None,
                "phantom_rate_count": round(1 - a["correct_count"] / model, 3) if model else None,
                "gdt_char_right_of_matched": f"{int(a['gdt_char_right'])}/{int(a['correct_loc'])}"
                if typ == "gdt"
                else "",
            }
        )
    with (RESULTS / "scores.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(r)
    for setting in ("off", "on"):
        p = totals[(setting, "_pages")]
        if p["pages"]:
            print(
                f"{setting}: {int(p['pages'])} pages, ${p['cost_usd']:.3f}, "
                f"{p['latency_s'] / p['pages']:.0f} s/page, "
                f"{p['output_tokens'] / p['pages']:.0f} output tokens/page"
            )


if __name__ == "__main__":
    main()
