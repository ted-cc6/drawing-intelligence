"""Run stage-2 understanding (qwen3-vl-plus, thinking off and on) over the 10 Spike D drawings. Budget <= $1.

Uses the package functions directly: extract_pdf(pdf, out_dir) writes the images, understand_page() makes the
call. Every page reply is saved to out/runs/<drawing>/page_<n>_<setting>.json.

Cost safety:
- Resumable: a page/setting whose reply file exists is skipped, so a re-run never pays twice.
- A hard guard stops before total spend crosses MAX_TOTAL_USD.
- --dry runs ONE page with thinking off, prints its cost and the projected total, and stops.

Run:
    python spikes/spike_d_symbols/run_understand.py --dry
    python spikes/spike_d_symbols/run_understand.py
    python spikes/spike_d_symbols/run_understand.py --settings on --only "PRF83A106004002,P23Y5B071019001"

Thinking on can take over 10 minutes for one page: set DI_API_TIMEOUT_S=1200 (the default 600 s timed out).
"""

from __future__ import annotations

import argparse
import json

from common import DRAWINGS, MODEL, OUT, build_client

from drawing_intelligence.extraction.pipeline import extract_pdf
from drawing_intelligence.understanding.understand import understand_page

MAX_TOTAL_USD = 0.95
SETTINGS = ("off", "on")
RUNS = OUT / "runs"


def spent() -> float:
    return sum(json.loads(p.read_text(encoding="utf-8"))["cost_usd"] for p in RUNS.rglob("page_*.json"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--settings", default=",".join(SETTINGS))
    ap.add_argument("--only", default="", help="comma-separated drawing names (default: all 10)")
    args = ap.parse_args()
    client = build_client()
    n_pages = 0
    for setting in args.settings.split(","):
        for name, pdf in DRAWINGS.items():
            if args.only and name not in args.only.split(","):
                continue
            work = OUT / "extract" / name
            extraction = extract_pdf(pdf, work)
            n_pages += len(extraction.pages) if setting == "off" else 0
            for page in extraction.pages:
                dest = RUNS / name / f"page_{page.page_number}_{setting}.json"
                if dest.exists():
                    continue
                if spent() >= MAX_TOTAL_USD:
                    print(f"budget guard: ${spent():.3f} spent, stopping")
                    return
                result = understand_page(client, page, work, model=MODEL, thinking=setting)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(result.model_dump_json(indent=1), encoding="utf-8")
                n_sym = len(result.knowledge.symbols) if result.knowledge else None
                print(
                    f"{name} p{page.page_number} {setting}: ${result.cost_usd:.4f} {result.latency_s:.0f}s "
                    f"valid={result.valid} symbols={n_sym} total=${spent():.3f}",
                    flush=True,
                )
                if args.dry:
                    total_pages = sum(len(extract_pdf(p).pages) for p in DRAWINGS.values())
                    projected = result.cost_usd * total_pages
                    print(f"projected thinking-off total for {total_pages} pages: ${projected:.3f}")
                    return


if __name__ == "__main__":
    main()
