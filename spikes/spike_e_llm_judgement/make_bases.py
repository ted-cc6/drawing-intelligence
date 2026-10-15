"""Collect the base DrawingKnowledge JSONs for Spike E into out/bases/ ($ small, Qwen only).

- The 4 samples already have a saved qwen understanding in data/baseline/ - copy those (free, read-only).
- The 2 round client parts have no saved understanding - run stage 1 + stage 2 once each
  (~$0.01, qwen3-vl-plus), writing images into out/ (git-ignored), never into data/.

Run: python spikes/spike_e_llm_judgement/make_bases.py
"""

from __future__ import annotations

import shutil
import warnings
from pathlib import Path

from common import BASES, build_client, read_json, write_json

from drawing_intelligence.extraction.pipeline import extract_pdf
from drawing_intelligence.settings import get_settings
from drawing_intelligence.understanding.understand import understand_page

DATA = get_settings().data_path
PRISMATIC = DATA / "client_set" / "Generic Prismatic Parts"
ROUND = DATA / "client_set" / "Generic Round Parts (Pins, Shafts)"

# Reuse the saved qwen understanding for the 4 samples (prismatic bases).
REUSE = {
    "B1_cam_plate": "10K_CAM PLATE",
    "B2_cylinder_rod": "10K_CYLINDER ROD MTG_02",
    "B4_pipe_clamp_block": "31K_PIPE CLAMP BLK_02",
}
# Round client parts with a REAL material - generate understanding once.
GENERATE = {
    "B5_pin_sleeve": ROUND / "45K_TCP_PIN_SLEEVE.pdf",
    "B6_coupling_spacer": ROUND / "19500_COUPLING SPACER.pdf",
}


def reuse_sample(tag: str, drawing: str) -> None:
    src = get_settings().baseline_dir / "understanding" / "qwen" / drawing / "drawing_knowledge.json"
    dst = BASES / f"{tag}.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    k = read_json(dst)
    print(f"  {tag:22s} reused  material={k['drawing']['material']!r}  dims={len(k['dimensions'])}")


def generate_round(tag: str, pdf: Path, client) -> None:
    img_dir = BASES / "_images" / tag
    ex = extract_pdf(pdf, out_dir=img_dir)  # images into out/ (git-ignored), not data/
    res = understand_page(client, ex.pages[0], img_dir)
    if not res.valid or res.knowledge is None:
        print(f"  {tag:22s} FAILED understanding: {res.problems}")
        return
    write_json(BASES / f"{tag}.json", res.knowledge)
    k = res.knowledge
    print(
        f"  {tag:22s} built   material={k.drawing.material!r}  dims={len(k.dimensions)} "
        f"feat={len(k.features)}  cost=${res.cost_usd:.4f}  {res.latency_s:.1f}s"
    )


def main() -> None:
    warnings.filterwarnings("ignore")
    print("Reusing saved sample understandings:")
    for tag, drawing in REUSE.items():
        reuse_sample(tag, drawing)
    print("Generating round-part bases (Qwen vision):")
    client = build_client()
    for tag, pdf in GENERATE.items():
        generate_round(tag, pdf, client)
    print(f"\nbases in {BASES}")


if __name__ == "__main__":
    main()
