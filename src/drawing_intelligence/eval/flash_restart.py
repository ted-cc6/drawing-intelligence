"""Independent Flash evaluation: select unseen PDFs, predict, label and score.

Starts without any old manifest, checkpoint, cache or cost ledger.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
import random
import re
import shutil
import sqlite3
import subprocess
import tempfile
from collections import Counter
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pymupdf
import yaml

from drawing_intelligence.eval.heldout import client_pdfs, development_sample

NEW_RUN_SOFT_CAP_USD = 2.50
FLASH_SPEC = {
    "provider": "qwen",
    "label": "Qwen3.8 Flash",
    "roles": ["review"],
    "capabilities": {"vision": True, "strict_json_schema": True},
    "max_output_tokens": 32000,
    "temperature": 0,
    "price": {
        "input_per_mtok": 0.15,
        "output_per_mtok": 0.47,
        "verified_on": "2026-10-31",
        "source": "https://www.alibabacloud.com/help/en/model-studio/qwen3-8-flash",
    },
    "thinking": {
        "default": "off",
        "options": {
            "off": {"extra_body": {"enable_thinking": False}},
            "on": {"extra_body": {"enable_thinking": True}},
        },
    },
}

LABELS = {"correct", "incorrect", "unsure"}
COLUMNS = [
    "finding_key", "drawing", "pdf_sha256", "finding_id", "rule", "category", "checked_by",
    "result", "severity", "comment", "evidence", "label", "label_reason", "labelled_by",
]  # fmt: skip


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def object_digest(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def endpoint_url(root: Path, override: str = "") -> str:
    config = yaml.safe_load((root / "config/models.yaml").read_text())
    value = override.strip() or config["providers"]["qwen"]["base_url"]
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        raise ValueError("use an HTTPS Qwen base URL without credentials, query parameters or fragments")
    return value.rstrip("/")


def drawing_stem(value: str) -> str:
    name = Path(value).name.lower()
    return name[:-4] if name.endswith(".pdf") else name


def fingerprint(path: Path) -> tuple[str, str]:
    with pymupdf.open(path) as doc:
        text = "\n".join(str(page.get_text()) for page in doc)
    normal = re.sub(r"\s+", "", text.upper())
    return digest(path), hashlib.sha256(normal.encode()).hexdigest() if normal else ""


def snapshot(root: Path) -> dict[str, Any]:
    tracked = subprocess.check_output(["git", "ls-files", "src", "config"], cwd=root, text=True).splitlines()
    return {
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "files": {name: digest(root / name) for name in tracked},
        "evaluation_driver_sha256": digest(Path(__file__)),
    }


def freeze(
    root: Path,
    destination: Path,
    n: int = 24,
    seed: int = 2026103102,
    *,
    qwen_base_url: str = "",
    team_exclusions_note: str = "",
) -> dict[str, Any]:
    """Exclude both dev sweeps, samples, historical held-outs, seeded bases and known spike inputs.

    The all-corpus extraction smoke test is not a judgment/calibration exposure. Additional private exposures
    must be supplied in data/eval/additional_exclusions.txt BEFORE freezing (client-relative paths).
    """
    extra = root / "data/eval/additional_exclusions.txt"
    endpoint = endpoint_url(root, qwen_base_url)
    if not team_exclusions_note.strip():
        raise ValueError("record who confirmed the team's additional calibration exclusions and when")
    if destination.exists():
        manifest = json.loads(destination.read_text())
        if manifest["snapshot"] != snapshot(root):
            raise ValueError("snapshot changed; frozen evaluation cannot be reused for a changed reviewer")
        if (
            manifest["n"],
            manifest["seed"],
            manifest["qwen_base_url"],
            manifest["additional_exclusions_sha256"],
            manifest["team_exclusions_note"],
        ) != (n, seed, endpoint, digest(extra) if extra.exists() else None, team_exclusions_note.strip()):
            raise ValueError("frozen selection/protocol changed; preserve the original manifest")
        return manifest
    if n <= 0:
        raise ValueError("n must be positive")
    subprocess.run(["git", "diff", "--exit-code", "--", "src", "config"], cwd=root, check=True)
    client = root / "data/client_set"
    files = client_pdfs(client)
    banned: set[Path] = set(development_sample(client))
    stems = {p.stem.lower() for p in (root / "data/raw").glob("*.[pP][dD][fF]")}
    # All historical eval CSVs, including all tuning rounds, not just the latest one.
    for p in (root / "data/eval").rglob("*.csv"):
        with p.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                for col in ("drawing", "source_file", "base"):
                    if row.get(col):
                        stems.add(drawing_stem(row[col]))
    for p in (root / "data/eval/seeded").glob("*/case.json"):
        base = json.loads(p.read_text()).get("base")
        if base:
            stems.add(drawing_stem(base))
    for p in (root / "data/eval").rglob("*drawings*.txt"):
        for line in p.read_text().splitlines():
            if line.strip():
                stems.add(drawing_stem(line.strip()))
    if extra.exists():
        for line in extra.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                path = (client / line.strip()).resolve()
                path.relative_to(client.resolve())
                if not path.is_file():
                    raise ValueError(f"unknown additional exclusion: {line}")
                banned.add(path)
                stems.add(path.stem.lower())
    # Spike source mentions: conservative exact stem matches in small text metadata, never cache replies.
    metadata = "\n".join(
        p.read_text(errors="replace").lower()
        for p in (root / "spikes").rglob("*")
        if p.suffix in {".json", ".csv", ".txt", ".yaml", ".py", ".md"} and p.stat().st_size < 2_000_000
    )
    banned |= {p for p in files if p.stem.lower() in stems or p.stem.lower() in metadata}
    fps = {p: fingerprint(p) for p in files}
    # Raw sample aliases and duplicated PDFs excluded by bytes AND normalised text.
    banned_fps = [fps[p] for p in banned if p in fps]
    banned_fps += [fingerprint(p) for p in (root / "data/raw").glob("*.[pP][dD][fF]")]
    hashes = {a for a, _ in banned_fps}
    texts = {b for _, b in banned_fps if b}
    candidates: list[Path] = []
    used_bytes: set[str] = set()
    used_texts: set[str] = set()
    used_stems: set[str] = set()
    for p in files:
        folders = p.relative_to(client).parts[:-1]
        if any("guideline" in f.lower() or "template" in f.lower() for f in folders):
            continue
        a, b = fps[p]
        if p in banned or a in hashes or (b and b in texts):
            continue
        if a in used_bytes or (b and b in used_texts) or p.stem.lower() in used_stems:
            continue
        candidates.append(p)
        used_bytes.add(a)
        used_texts.add(b)
        used_stems.add(p.stem.lower())
    if len(candidates) < n:
        raise ValueError(f"only {len(candidates)} eligible drawings; requested {n}")
    selected = sorted(random.Random(seed).sample(candidates, n))
    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "owner": "Zhetao Zhang",
        "qwen_base_url": endpoint,
        "team_exclusions_note": team_exclusions_note.strip(),
        "models": {"understand": "qwen3-vl-plus", "review": "qwen3.8-flash", "thinking": "off"},
        "seed": seed,
        "n": n,
        "eligible": len(candidates),
        "snapshot": snapshot(root),
        "exclusion_policy": "dev seeds 1/2 n=200; raw; all historical heldout rounds; seeded bases; "
        "spike metadata; additional_exclusions; byte/text duplicates; guideline/template folders",
        "additional_exclusions_sha256": digest(extra) if extra.exists() else None,
        "limitation": "Private calibration is not detectable; confirm team exclusions before freeze.",
        "drawings": [
            {"path": p.relative_to(client).as_posix(), "sha256": fps[p][0], "text_sha256": fps[p][1]}
            for p in selected
        ],
        "evaluation_kind": "fresh_flash_evaluation",
        "runtime_flash_model_spec": copy.deepcopy(FLASH_SPEC),
        "budget_policy": {
            "new_run_soft_cap_usd": NEW_RUN_SOFT_CAP_USD,
            "prior_cost_reserve_usd": 0.50,
            "session_soft_budget_usd": 3.00,
        },
        "model_note": "Flash reviewer variant; not validation of the original Max baseline.",
        "protocol": {
            "precision_only": True,
            "labels": sorted(LABELS),
            "no_prompt_or_rule_tuning": True,
            "one_primary_run": True,
        },
    }
    dump(destination, manifest)
    destination.with_name("drawings.txt").write_text(
        "\n".join(r["path"] for r in manifest["drawings"]) + "\n", encoding="utf-8"
    )
    return manifest


def billed(database: Path) -> float:
    if not database.exists():
        return 0.0
    # closing(): sqlite3's own context manager only commits; Windows cannot delete an open file.
    with closing(sqlite3.connect(database)) as conn:
        return float(conn.execute("SELECT COALESCE(SUM(cost_usd),0) FROM llm_calls").fetchone()[0])


def run_once(
    root: Path,
    out: Path,
    *,
    approved_soft_budget_usd: float,
    approval_note: str,
) -> dict[str, Any]:
    """Budget checked BETWEEN drawings. It may be exceeded by one drawing; not a hard billing cap.

    Completed/failed attempts are preserved and never silently regenerated. Fresh cache is shared only within
    this frozen evaluation. API failures are reported, never counted as zero findings or replaced in sample.
    """
    from drawing_intelligence.graph import run_workflow
    from drawing_intelligence.schemas import ReviewerOutput
    from drawing_intelligence.settings import Settings

    manifest = json.loads((out / "manifest.json").read_text())
    if manifest["snapshot"] != snapshot(root):
        raise ValueError("reviewer snapshot differs from the frozen manifest")
    if (
        not math.isfinite(approved_soft_budget_usd)
        or not 0 < approved_soft_budget_usd <= NEW_RUN_SOFT_CAP_USD
    ):
        raise ValueError("explicit positive budget at or below the $2.50 new-run cap required")
    if not approval_note.strip():
        raise ValueError("record the user approval and date before paid calls")
    if not manifest.get("team_exclusions_note"):
        raise ValueError("team calibration exclusions have not been confirmed")
    runtime_config = out / "runtime_config"
    shutil.copytree(root / "config", runtime_config, dirs_exist_ok=True)
    model_file = runtime_config / "models.yaml"
    models = yaml.safe_load(model_file.read_text())
    models["providers"]["qwen"]["base_url"] = manifest["qwen_base_url"]
    models.setdefault("models", {})["qwen3.8-flash"] = manifest.get("runtime_flash_model_spec", FLASH_SPEC)
    models.setdefault("defaults", {})["review"] = "qwen3.8-flash"
    model_file.write_text(yaml.safe_dump(models, sort_keys=False), encoding="utf-8")
    settings = Settings(
        data_dir=(out / "runtime_data").resolve(), config_dir=runtime_config.resolve(), retention="keep"
    )
    if not settings.api_key("QWEN_API_KEY"):
        raise ValueError("QWEN_API_KEY missing; set a Colab secret or use getpass")
    state_file = out / "run_state.json"
    state: dict[str, Any] = (
        json.loads(state_file.read_text())
        if state_file.exists()
        else {"manifest_sha256": digest(out / "manifest.json"), "runs": [], "rows": []}
    )
    if state["manifest_sha256"] != digest(out / "manifest.json"):
        raise ValueError("manifest changed after predictions started")
    if any(r["status"] != "ok" for r in state["runs"]):
        raise ValueError(
            "unresolved failed/interrupted attempt; archive an authorized infrastructure retry first"
        )
    if (state["runs"] or state.get("estimated_billed_usd", 0) > 0) and not settings.telemetry_db.exists():
        raise ValueError("cost ledger missing; restore the complete checkpoint before resuming")
    if state.get("rows_sha256") and state["rows_sha256"] != object_digest(state["rows"]):
        raise ValueError("prediction rows changed")
    from drawing_intelligence.storage import Telemetry

    ledger = Telemetry(settings.telemetry_db)  # creates the schema only
    if callable(getattr(ledger, "close", None)):
        ledger.close()
    state.setdefault("budget_approvals", []).append(
        {
            "at": datetime.now(UTC).isoformat(),
            "note": approval_note.strip(),
            "soft_budget_usd": approved_soft_budget_usd,
        }
    )
    dump(out / "budget_approval.json", state["budget_approvals"])
    attempted = {r["path"] for r in state["runs"]}
    for entry in manifest["drawings"]:
        if entry["path"] in attempted:
            continue
        if billed(settings.telemetry_db) >= approved_soft_budget_usd:
            break
        pdf = root / "data/client_set" / entry["path"]
        if digest(pdf) != entry["sha256"]:
            raise ValueError("frozen PDF changed")
        run: dict[str, Any] = {"path": entry["path"], "status": "started", "errors": ["InterruptedError"]}
        # Persist a started attempt BEFORE calling the API; interruption is visible and cannot silently rerun.
        state["runs"].append(run)
        dump(state_file, state)
        try:
            run["errors"] = []
            with tempfile.TemporaryDirectory(prefix="di-fresh-") as temp:
                settings_for_run = settings.model_copy(update={"sessions_root": Path(temp)})
                res = run_workflow(
                    pdf,
                    settings_for_run,
                    understand=True,
                    review=True,
                    model="qwen3-vl-plus",
                    thinking="off",
                    review_model="qwen3.8-flash",
                    review_thinking="off",
                    export_dir=out / "reports",
                )
            assert res.review is not None and res.exported_to is not None
            run["session_id"] = res.session_id
            run["pages"] = res.extraction.n_pages
            if len(res.understanding) != res.extraction.n_pages or not all(
                u.valid for u in res.understanding
            ):
                run["errors"].append("understanding absent or invalid")
            for reviewer in ("drawing_practice", "manufacturability", "design_intent"):
                f = res.exported_to / f"{reviewer}.json"
                if not f.exists():
                    run["errors"].append(f"missing reviewer: {reviewer}")
                    continue
                output = ReviewerOutput.model_validate_json(f.read_text())
                if output.error:
                    run["errors"].append(f"{reviewer}: {output.error.split(':', 1)[0]}")
            run["rejected_findings"] = len(res.rejected)
            # Baseline reviewers can suppress malformed JSON as an empty finding list. Do not
            # count that as a successful zero-issue drawing in this evaluation.
            for cached in settings.cache_dir.glob("*.json"):
                response = json.loads(cached.read_text())
                if response.get("model") != "qwen3.8-flash":
                    continue
                try:
                    payload = json.loads(response.get("text", ""))
                    if not isinstance(payload, dict) or not isinstance(payload.get("findings"), list):
                        raise ValueError("missing findings array")
                except (ValueError, TypeError):
                    run["errors"].append("invalid reviewer JSON")
            run["status"] = "ok" if not run["errors"] else "failed"
            for f in res.review.findings:
                state["rows"].append(
                    {
                        "finding_key": entry["sha256"] + ":" + f.id,
                        "drawing": entry["path"],
                        "pdf_sha256": entry["sha256"],
                        "finding_id": f.id,
                        "rule": f.rule_id,
                        "category": f.category,
                        "checked_by": "llm:" + f.reviewer if f.source == "llm" else f.source,
                        "result": f.result,
                        "severity": f.severity,
                        "comment": f.comment,
                        "evidence": json.dumps([e.model_dump() for e in f.evidence], ensure_ascii=False),
                        "label": "",
                        "label_reason": "",
                        "labelled_by": "",
                    }
                )
        except Exception as exc:
            run["status"] = "failed"
            run["errors"].append(type(exc).__name__)  # never write an exception that may echo a secret
        state["estimated_billed_usd"] = billed(settings.telemetry_db)
        state["rows_sha256"] = object_digest(state["rows"])
        dump(state_file, state)
        print(
            f"{len(state['runs'])}/{manifest['n']} attempted; {run['status']}; "
            f"estimated billed ${state['estimated_billed_usd']:.4f}",
            flush=True,
        )
        if run["status"] != "ok":
            break  # fix infrastructure first; do not multiply an authentication/schema failure
    # Originals are immutable after prediction; labels go in a separate copy.
    with (out / "findings_unlabelled.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, COLUMNS)
        writer.writeheader()
        writer.writerows(state["rows"])
    state["complete"] = len(state["runs"]) == manifest["n"] and all(
        r["status"] == "ok" for r in state["runs"]
    )
    dump(state_file, state)
    return state


def authorize_infrastructure_retry(out: Path, reason: str) -> int:
    """Archive failed attempts before explicitly retrying infrastructure errors on the SAME sample.

    Successful outputs/cache are retained. Schema/quality failures cannot be discarded to obtain a nicer run.
    """
    if not reason.strip():
        raise ValueError("a documented infrastructure correction is required")
    state_file = out / "run_state.json"
    state = json.loads(state_file.read_text())
    metrics_file = out / "metrics.json"
    if metrics_file.exists() and json.loads(metrics_file.read_text()).get("status") == "final":
        raise ValueError("final evaluation cannot be regenerated")
    failures = [r for r in state["runs"] if r["status"] != "ok"]
    allowed = {
        "AuthenticationError",
        "PermissionDeniedError",
        "RateLimitError",
        "APITimeoutError",
        "APIConnectionError",
        "MissingKeyError",
        "TimeoutError",
        "ConnectionError",
        "InterruptedError",
        "InternalServerError",
    }
    for run in failures:
        if run["errors"] and any(e.rsplit(": ", 1)[-1] not in allowed for e in run["errors"]):
            raise ValueError("non-infrastructure failure: retain it; do not rerun to improve outputs")
    if not failures:
        return 0
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    archive = out / "failed_attempts" / stamp
    archive.mkdir(parents=True)
    dump(archive / "state_before_retry.json", state)
    dump(archive / "authorization.json", {"reason": reason, "at": stamp})
    paths = {r["path"] for r in failures}
    for name in paths:
        report = out / "reports" / Path(name).stem
        if report.exists():
            shutil.copytree(report, archive / Path(name).stem)
    state.setdefault("infrastructure_retry_audit", []).append(
        {"at": stamp, "reason": reason, "failed_paths": sorted(paths)}
    )
    state["runs"] = [r for r in state["runs"] if r["path"] not in paths]
    state["rows"] = [r for r in state["rows"] if r["drawing"] not in paths]
    state["rows_sha256"] = object_digest(state["rows"])
    state["complete"] = False
    dump(state_file, state)
    return len(failures)


def wilson(correct: int, decided: int) -> list[float] | None:
    if decided == 0:
        return None
    p, z = correct / decided, 1.959963984540054
    denom = 1 + z * z / decided
    centre = (p + z * z / (2 * decided)) / denom
    half = z * math.sqrt(p * (1 - p) / decided + z * z / (4 * decided * decided)) / denom
    return [max(0, centre - half), min(1, centre + half)]


def metrics(rows: list[dict[str, str]]) -> dict[str, Any]:
    counts = Counter(r["label"].strip().lower() for r in rows)
    c, i, u = (counts[x] for x in ("correct", "incorrect", "unsure"))
    total, decided = len(rows), c + i
    return {
        "findings": total,
        "correct": c,
        "incorrect": i,
        "unsure": u,
        "precision_decided": c / decided if decided else None,
        "wilson_95_findings_independent_assumption": wilson(c, decided),
        "conservative_all_unsure_wrong": c / total if total else None,
        "optimistic_all_unsure_right": (c + u) / total if total else None,
    }


def score(out: Path, labelled_csv: Path, *, confirmation: str = "") -> dict[str, Any]:
    state = json.loads((out / "run_state.json").read_text())
    manifest = json.loads((out / "manifest.json").read_text())
    if state["manifest_sha256"] != digest(out / "manifest.json"):
        raise ValueError("manifest changed after predictions started")
    if state.get("rows_sha256") != object_digest(state["rows"]):
        raise ValueError("prediction rows changed")
    expected = {r["path"] for r in manifest["drawings"]}
    attempted = [r["path"] for r in state["runs"]]
    if len(set(attempted)) != len(attempted) or not set(attempted) <= expected:
        raise ValueError("run ledger contains duplicate or unexpected drawings")
    with labelled_csv.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    gold = {r["finding_key"]: r for r in state["rows"]}
    if len(gold) != len(state["rows"]):
        raise ValueError("duplicate prediction keys")
    if len(rows) != len(gold) or {r["finding_key"] for r in rows} != set(gold):
        raise ValueError("labels must cover exactly the original predictions; no drops/additions/duplicates")
    for row in rows:
        original = gold[row["finding_key"]]
        for col in COLUMNS:
            if col not in {"label", "label_reason", "labelled_by"} and row.get(col, "") != str(
                original.get(col) or ""
            ):
                raise ValueError(f"prediction column edited: {col}")
        if (
            row["label"].strip().lower() not in LABELS
            or not row["label_reason"].strip()
            or not row["labelled_by"].strip()
        ):
            raise ValueError(
                "every finding needs correct/incorrect/unsure, a reason, and an independent labeler"
            )
    successful = {r["path"] for r in state["runs"] if r["status"] == "ok"}
    complete = successful == expected and len(attempted) == manifest["n"]
    excluded_failed_rows = sum(r["drawing"] not in successful for r in rows)
    rows = [r for r in rows if r["drawing"] in successful]
    groups = {
        "code_lookup": [r for r in rows if not r["checked_by"].startswith("llm:")],
        "ai_reviewers": [r for r in rows if r["checked_by"].startswith("llm:")],
    }
    result: dict[str, Any] = {
        "status": "final"
        if complete and confirmation.strip() and manifest.get("team_exclusions_note")
        else "PROVISIONAL",
        "engineer_confirmation": confirmation,
        "models": manifest.get(
            "models", {"understand": "qwen3-vl-plus", "review": "qwen3.8-flash", "thinking": "off"}
        ),
        "evaluation_kind": "fresh_flash_evaluation",
        "excluded_failed_rows": excluded_failed_rows,
        "completed_drawings": sum(r["status"] == "ok" for r in state["runs"]),
        "attempted_drawings": len(state["runs"]),
        "planned_drawings": manifest["n"],
        "manifest_sha256": state["manifest_sha256"],
        "estimated_billed_usd": state.get("estimated_billed_usd", 0),
        "cost_note": "Estimate uses repository registry rates, not the provider invoice; "
        "failed calls may have unreported cost.",
        "labels_sha256": digest(labelled_csv),
        "groups": {k: metrics(v) for k, v in groups.items()},
        "by_reviewer": {
            k: metrics([r for r in rows if r["checked_by"] == k])
            for k in sorted({r["checked_by"] for r in rows})
        },
        "by_ai_rule": {
            k: metrics([r for r in groups["ai_reviewers"] if r["rule"] == k])
            for k in sorted({r["rule"] for r in groups["ai_reviewers"]})
        },
        "limits": "Precision of pipeline-verified raised findings only; no recall claim. "
        "Wilson assumes independent findings; "
        "Findings cluster by drawing; use the drawing-cluster bootstrap. "
        "Failed/incomplete runs remain provisional.",
    }
    # Drawing-cluster bootstrap includes successful drawings with zero AI findings.
    ai = groups["ai_reviewers"]
    drawings = [r["path"] for r in state["runs"] if r["status"] == "ok"]
    per_drawing = {d: [r for r in ai if r["drawing"] == d] for d in drawings}
    boot: list[float] = []
    rng = random.Random(42)
    for _ in range(3000):
        sample = (
            [r for d in rng.choices(drawings, k=len(drawings)) for r in per_drawing[d]] if drawings else []
        )
        value = metrics(sample)["precision_decided"]
        if value is not None:
            boot.append(value)
    boot.sort()
    result["ai_drawing_cluster_bootstrap_95"] = (
        [boot[int(0.025 * len(boot))], boot[min(len(boot) - 1, int(0.975 * len(boot)))]] if boot else None
    )
    dump(out / "metrics.json", result)
    primary = result["groups"]["ai_reviewers"]
    rate = primary["precision_decided"]
    percent = f"{rate:.1%}" if rate is not None else "undefined (no decided AI findings)"
    summary = (
        f"# Fresh Flash reviewer evaluation — {result['status']}\n\n"
        f"Baseline: `{manifest['snapshot'].get('commit', 'fixture')}`. "
        f"Completed {len(successful)}/{manifest['n']} frozen drawings.\n\n"
        f"AI correct: {primary['correct']}; incorrect: {primary['incorrect']}; "
        f"unsure: {primary['unsure']}. Decided precision: **{percent}**.\n\n"
        "Precision = correct / (correct + incorrect). See metrics.json for unsure bounds, "
        "drawing-cluster bootstrap interval, code/AI separation and breakdowns. "
        "No recall is measured. Zero findings do not prove compliance. "
        "The historical tuned-set 88% is not this fresh result.\n\n"
        "Reviewer model: `qwen3.8-flash`; understanding: `qwen3-vl-plus`.\n\n"
        "This evaluates the Flash variant, not the original Max baseline.\n\n"
        f"Engineer confirmation: {confirmation or 'pending'}.\n"
    )
    (out / "README.md").write_text(summary, encoding="utf-8")
    return result
