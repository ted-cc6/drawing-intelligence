"""Prepare or explicitly run the separate Qwen3.7-Plus evaluation from repo root."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Authorize actual billed API calls")
    parser.add_argument("--budget-usd", type=float, default=1.0, help="Soft cap, checked between PDFs")
    parser.add_argument("--approval-note", default="", help="Personal payer authorization for this run")
    parser.add_argument("--out", type=Path, default=HERE / "out" / "run24")
    args = parser.parse_args()
    if not math.isfinite(args.budget_usd) or args.budget_usd <= 0:
        parser.error("--budget-usd must be finite and positive")
    if args.run and (not args.approval_note.strip() or not os.environ.get("QWEN_API_KEY", "").strip()):
        parser.error("--run needs QWEN_API_KEY and an explicit --approval-note")
    endpoint = os.environ.get("QWEN_BASE_URL", "").strip().rstrip("/")
    parts = urlsplit(endpoint)
    if not (
        parts.scheme == "https"
        and parts.hostname
        and parts.hostname.endswith(".us-east-1.maas.aliyuncs.com")
        and parts.path == "/compatible-mode/v1"
        and not any((parts.username, parts.password, parts.query, parts.fragment))
    ):
        parser.error("Set QWEN_BASE_URL to your Virginia workspace HTTPS /compatible-mode/v1 URL")
    frozen = json.loads((HERE / "frozen_inputs.json").read_text(encoding="utf-8"))
    for entry in frozen["drawings"]:
        pdf = ROOT / "data/client_set" / entry["path"]
        if not pdf.is_file() or hashlib.sha256(pdf.read_bytes()).hexdigest() != entry["sha256"]:
            parser.error(f"Frozen PDF missing or changed: {entry['path']}")
    evidence_manifest = (
        ROOT / "data/eval/heldout/2026-11-03_qwen37plus_virginia_global_same24/full/manifest.json"
    )
    source_hashes = json.loads(evidence_manifest.read_text(encoding="utf-8"))["files"]
    for name, expected in source_hashes.items():
        if name.startswith("src/"):
            source_file = ROOT / name
            if not source_file.is_file() or hashlib.sha256(source_file.read_bytes()).hexdigest() != expected:
                parser.error(f"Audited source changed: {name}. Review protocol before starting a new run.")
    out = args.out.resolve()
    # Configuration lives beside the output, keeping a new held-out folder initially empty.
    config = out.parent / (out.name + "_config")
    if not config.exists():
        shutil.copytree(ROOT / "config", config)
    snapshot = yaml.safe_load((HERE / "models.snapshot.yaml").read_text(encoding="utf-8"))
    snapshot["providers"]["qwen"]["base_url"] = endpoint
    config_text = yaml.safe_dump(snapshot, sort_keys=False, allow_unicode=True)
    target = config / "models.yaml"
    if not target.exists() or target.read_text(encoding="utf-8") != config_text:
        target.write_text(config_text, encoding="utf-8")
    env = {**os.environ, "DI_CONFIG_DIR": str(config), "DI_RETENTION": "keep"}
    command = [
        "eval",
        "heldout",
        "--out",
        str(out),
        "--drawings",
        str(HERE / "drawings24.txt"),
        "--exclusions-note",
        frozen["team_exclusions_note"],
    ]
    # Free preflight verifies the frozen PDFs and validates the installed native evaluator.
    subprocess.run(
        [sys.executable, "-c", "from drawing_intelligence.cli import app; app()", *command, "--prepare-only"],
        cwd=ROOT,
        env=env,
        check=True,
    )
    if not args.run:
        print("Prepared only. No API calls. Pass --run, --approval-note and a budget to execute.")
        return
    infra = out / "infrastructure"
    infra.mkdir(exist_ok=True)
    env.update(
        {
            "MAX_RECOVERY_MODEL": "qwen3.7-plus",
            "MAX_RECOVERY_LOG": str(infra / "plus_recovery.jsonl"),
            "MAX_RECOVERY_WAITS": "15,45",
            "MAX_RECOVERY_CONTINUE": "1",
            "MAX_RECOVERY_CONSECUTIVE_LIMIT": "2",
            "MAX_FALLBACK_BASE_URL": "",
            "MAX_FALLBACK_API_KEY": "",
        }
    )
    print("Separate Plus run; cached results may be reused. Unknown failed-call charges are additional.")
    subprocess.run(
        [
            sys.executable,
            str(HERE / "transport.py"),
            *command,
            "--budget-usd",
            str(args.budget_usd),
            "--approval-note",
            args.approval_note,
            "--retry-note",
            args.approval_note + "; identical infrastructure retry, retain all attempts.",
            "--yes",
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )


if __name__ == "__main__":
    main()
