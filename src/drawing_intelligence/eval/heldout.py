"""Held-out validation: the review on client drawings nothing was built or tuned on, for an engineer to label.

The planted-error set measures recall, but its precision is optimistic: the checks and the LLM reviewers were
tuned on it. Here the review runs on drawings drawn at random from the client set, after leaving out every
drawing an earlier development sweep looked at (two random samples of 200, seeds 1 and 2, used to tune the
title-block parser and the check thresholds). Each finding goes into a CSV with empty label columns: an
engineer marks it `correct`, `incorrect` or `unsure`, which gives the precision a real review would have.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from drawing_intelligence.report.build import location, numbered
from drawing_intelligence.settings import PROJECT_ROOT, Settings

DEV_SAMPLE_SEEDS = (1, 2)  # the development sweeps' random samples (2026-10-23 to 10-25)
DEV_SAMPLE_SIZE = 200
LABEL_COLUMNS: tuple[str, ...] = (
    "drawing", "no", "rule", "category", "result", "severity", "checked_by", "comment", "location",
    "label", "label_reason", "labelled_by",
)  # fmt: skip
AUDIT_COLUMNS = (*LABEL_COLUMNS[:-3], "finding_key", "evidence", *LABEL_COLUMNS[-3:])
INFRASTRUCTURE_ERRORS = {
    "InternalServerError", "RateLimitError", "APITimeoutError", "APIConnectionError",
    "AuthenticationError", "PermissionDeniedError", "ConnectionError", "TimeoutError", "InterruptedError",
}  # fmt: skip


def _hash(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _save(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def freeze_heldout(
    settings: Settings,
    drawings: list[Path],
    out: Path,
    *,
    understand: bool = True,
    exclusions_note: str = "",
) -> dict[str, Any]:
    """Freeze the existing command's inputs and registry; no model registration or API calls."""
    from drawing_intelligence.llm import load_registry

    client = (settings.data_path / "client_set").resolve()
    entries = []
    for pdf in drawings:
        relative = pdf.resolve().relative_to(client)
        if pdf.suffix.lower() != ".pdf" or not pdf.is_file() or _not_a_drawing(pdf.resolve(), client):
            raise ValueError("held-out inputs must be drawing PDFs inside data/client_set")
        entries.append({"path": relative.as_posix(), "sha256": _file_hash(pdf)})
    if not entries or len({e["path"] for e in entries}) != len(entries):
        raise ValueError("provide a nonempty, unique drawing list")
    if len({e["sha256"] for e in entries}) != len(entries):
        raise ValueError("the sample contains duplicate PDF bytes")
    registry = load_registry(settings.config_path / "models.yaml")
    models = {role: registry.model(None, role).model_dump(mode="json") for role in ("understand", "review")}
    files = {}
    for prefix, folder in (("src", PROJECT_ROOT / "src"), ("config", settings.config_path)):
        for path in sorted(folder.rglob("*")):
            if path.is_file() and path.suffix in {".py", ".md", ".yaml"}:
                files[f"{prefix}/{path.relative_to(folder).as_posix()}"] = _file_hash(path)
    payload = {
        "version": 1,
        "drawings": entries,
        "n": len(entries),
        "understand": understand,
        "models": models,
        "providers": {k: v.model_dump() for k, v in registry.providers.items()},
        "files": files,
        "team_exclusions_note": exclusions_note.strip(),
        "protocol": "Registry defaults and unchanged prompts; no sample replacements; preserve all attempts.",
    }
    path = out / "manifest.json"
    if path.exists():
        frozen = json.loads(path.read_text(encoding="utf-8"))
        if {k: v for k, v in frozen.items() if k != "created_at"} != payload:
            raise ValueError("frozen drawing, model, source/config or exclusion settings changed")
        return frozen
    if out.exists() and any(out.iterdir()):
        raise ValueError("use a new output folder; do not overwrite an earlier evaluation")
    _save(path, {"created_at": datetime.now(UTC).isoformat(), **payload})
    (out / "drawings.txt").write_text("\n".join(e["path"] for e in entries) + "\n", encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_cached_reviewers(settings: Settings, result: Any) -> None:
    """Validate saved replies with the existing message/schema builders; never call the API."""
    from drawing_intelligence.extraction import load_template
    from drawing_intelligence.llm import LLMClient, TextPart, load_registry
    from drawing_intelligence.review import load_rulebook
    from drawing_intelligence.review.context import ReviewContext
    from drawing_intelligence.review.llm_reviewer import (
        AVAILABLE_INPUTS,
        build_message,
        needs_symbols,
        output_schema,
    )
    from drawing_intelligence.review.reviewers import LLM_REVIEWERS, reviewer_for
    from drawing_intelligence.storage import ResponseCache, Telemetry

    ctx = ReviewContext(
        extraction=result.extraction,
        rulebook=load_rulebook(settings.config_path / "rules"),
        template=load_template(result.extraction.template),
        knowledge={r.page_number: r.knowledge for r in result.understanding},
    )
    registry = load_registry(settings.config_path / "models.yaml")
    spec = registry.model(None, "review")
    cache = ResponseCache(settings.cache_dir)
    client = LLMClient(registry, settings, Telemetry(settings.telemetry_db), cache, result.session_id)
    for name in LLM_REVIEWERS:
        rules = [
            r
            for r in ctx.rulebook.rules
            if r.check_type == "llm"
            and reviewer_for(r) == name
            and r.applies(ctx.part_family, ctx.drawing_type)
            and not set(r.params.get("needs", [])) - AVAILABLE_INPUTS
        ]
        if not rules:
            continue
        schema = output_schema([r.id for r in rules], symbols=needs_symbols(rules))
        request = client.build_request(
            spec, [TextPart(build_message(ctx, rules))], schema, spec.thinking_level(None)
        )
        reply = cache.get(client.cache_key(request))
        if reply is None:
            raise ValueError("review response missing from the saved cache")
        schema.model_validate_json(reply["text"])  # arrays/invalid items stay failures; no format repair


def _record_rows(result: Any, drawing: str, pdf_hash: str) -> list[dict[str, str]]:
    from drawing_intelligence.extraction import load_template

    template = load_template(result.extraction.template)
    return [
        {
            "drawing": drawing,
            "no": str(nf.no),
            "rule": nf.finding.rule_id or "",
            "category": nf.finding.category,
            "result": nf.finding.result,
            "severity": nf.finding.severity,
            "checked_by": nf.finding.source if nf.finding.source != "llm" else f"llm:{nf.finding.reviewer}",
            "comment": nf.finding.comment,
            "location": location(nf.finding, result.extraction, template),
            "finding_key": f"{pdf_hash}:{nf.finding.id}",
            "evidence": json.dumps([e.model_dump() for e in nf.finding.evidence], ensure_ascii=False),
            "label": "",
            "label_reason": "",
            "labelled_by": "",
        }
        for nf in numbered(result.review)
    ]


def client_pdfs(client_dir: Path) -> list[Path]:
    return sorted(p for p in client_dir.rglob("*") if p.suffix.lower() == ".pdf")


def development_sample(client_dir: Path) -> set[Path]:
    """The drawings the development sweeps used, recreated exactly as they were drawn."""
    files = client_pdfs(client_dir)
    seen: set[Path] = set()
    for seed in DEV_SAMPLE_SEEDS:
        random.seed(seed)
        seen |= set(random.sample(files, DEV_SAMPLE_SIZE))
    return seen


def _not_a_drawing(path: Path, client_dir: Path) -> bool:
    """The client set also holds PARI's guideline documents and the template; they are not drawings."""
    folders = path.relative_to(client_dir).parts[:-1]
    return any("guideline" in f.lower() or "template" in f.lower() for f in folders)


def select_heldout(client_dir: Path, n: int, seed: int, samples_dir: Path | None = None) -> list[Path]:
    """`n` drawings at random (fixed seed) from those no development sweep looked at, and none of the sample
    drawings everything was built on (copies of them are in the client set too)."""
    samples = {p.stem.lower() for p in samples_dir.glob("*.pdf")} if samples_dir else set()
    seen = development_sample(client_dir)
    pool = [
        p
        for p in client_pdfs(client_dir)
        if p not in seen and p.stem.lower() not in samples and not _not_a_drawing(p, client_dir)
    ]
    return sorted(random.Random(seed).sample(pool, n))


@dataclass
class HeldoutRun:
    drawing: str
    exported_to: Path | None
    findings: int
    cost_usd: float
    variant_title_block: bool
    error: str | None = None


def _persist_state(out: Path, state: dict[str, Any], total: int) -> None:
    latest = {r["drawing"]: r for r in state["attempts"]}
    state["complete"] = len(latest) == total and all(r["status"] == "ok" for r in latest.values())
    state["estimated_billed_usd"] = sum(r.get("cost_usd", 0) for r in state["attempts"])
    state["rows_sha256"] = _hash(state["rows"])
    _save(out / "run_state.json", state)
    with (out / "findings.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, AUDIT_COLUMNS)
        writer.writeheader()
        writer.writerows(state["rows"])


def _capture_calls(settings: Settings, out: Path, attempt: dict[str, Any]) -> None:
    from drawing_intelligence.storage import Telemetry

    sessions = out / attempt["sessions_directory"]
    ids = {p.name for p in sessions.iterdir() if p.is_dir()} if sessions.exists() else set()
    ids.update(c["session_id"] for c in attempt.get("calls", []))
    if attempt.get("session_id"):
        ids.add(attempt["session_id"])
    calls = [r for r in Telemetry(settings.telemetry_db).calls() if r["session_id"] in ids]
    if any(previous not in calls for previous in attempt.get("calls", [])):
        raise ValueError("prior charged calls are missing or changed; restore the original telemetry ledger")
    attempt["calls"] = calls
    attempt["cost_usd"] = sum(r["cost_usd"] for r in calls)


def run_heldout(
    settings: Settings,
    drawings: list[Path],
    out_dir: Path,
    *,
    understand: bool = True,
    approved_budget_usd: float | None = None,
    approval_note: str = "",
    exclusions_note: str = "",
    retry_note: str = "",
) -> list[HeldoutRun]:
    """Run registry defaults once per PDF, resume successes, and audit only explicitly authorized retries.

    The budget is a registry-rate soft cap checked BETWEEN drawings; one drawing may exceed it.
    Run only one process per output folder. Raw reports/cache and all failed attempts are retained.
    """
    from drawing_intelligence.graph import run_workflow
    from drawing_intelligence.review.reviewers import LLM_REVIEWERS
    from drawing_intelligence.schemas import ReviewerOutput

    if understand and (
        not approved_budget_usd
        or not math.isfinite(approved_budget_usd)
        or approved_budget_usd <= 0
        or not approval_note.strip()
        or not exclusions_note.strip()
    ):
        raise ValueError(
            "paid evaluation requires explicit budget, Binjie's approval note and team exclusions"
        )
    manifest = freeze_heldout(
        settings, drawings, out_dir, understand=understand, exclusions_note=exclusions_note
    )
    manifest_hash = _file_hash(out_dir / "manifest.json")
    state_file = out_dir / "run_state.json"
    state = (
        json.loads(state_file.read_text(encoding="utf-8"))
        if state_file.exists()
        else {
            "manifest_sha256": manifest_hash,
            "attempts": [],
            "rows": [],
            "rows_sha256": _hash([]),
        }
    )
    if state["manifest_sha256"] != manifest_hash or state["rows_sha256"] != _hash(state["rows"]):
        raise ValueError("saved manifest or prediction rows changed")
    if not {r["drawing"] for r in state["attempts"]} <= {e["path"] for e in manifest["drawings"]}:
        raise ValueError("the attempt ledger contains drawings outside the frozen sample")
    if (out_dir / "metrics.json").exists() and json.loads((out_dir / "metrics.json").read_text()).get(
        "status"
    ) == "final":
        raise ValueError("final evaluation is immutable")
    latest = {r["drawing"]: r for r in state["attempts"]}
    failures = [r for r in latest.values() if r["status"] != "ok"]
    if failures:
        if not retry_note.strip():
            raise ValueError(
                "failed/interrupted attempt retained; supply an authorized infrastructure retry note"
            )
        if any(set(r["errors"]) - INFRASTRUCTURE_ERRORS for r in failures):
            raise ValueError(
                "schema/quality failures are retained and cannot be rerun as infrastructure retries"
            )
        archive = out_dir / "retry_audit" / f"{len(state['attempts']):04d}"
        if archive.exists():
            raise ValueError("retry already authorized; inspect the retained attempt before retrying again")
        _save(archive / "state_before_retry.json", state)
        _save(
            archive / "authorization.json",
            {
                "at": datetime.now(UTC).isoformat(),
                "reason": retry_note.strip(),
                "manifest_sha256": manifest_hash,
                "drawings": [r["drawing"] for r in failures],
            },
        )
        for attempt in failures:
            if attempt["status"] == "started":
                _capture_calls(settings, out_dir, attempt)
                attempt["status"] = "failed"
    state.setdefault("budget_approvals", []).append(
        {
            "at": datetime.now(UTC).isoformat(),
            "soft_budget_usd": approved_budget_usd,
            "note": approval_note,
        }
    )
    _persist_state(out_dir, state, manifest["n"])
    for pdf, entry in zip(drawings, manifest["drawings"], strict=True):
        if entry["path"] in latest and latest[entry["path"]]["status"] == "ok":
            continue
        if understand and state["estimated_billed_usd"] >= (approved_budget_usd or 0):
            break
        if _file_hash(pdf) != entry["sha256"]:
            raise ValueError("a frozen PDF changed during evaluation")
        number = len(state["attempts"]) + 1
        sessions = out_dir / "_runtime_sessions" / f"{number:04d}"
        attempt = {
            "drawing": entry["path"],
            "status": "started",
            "errors": ["InterruptedError"],
            "sessions_directory": sessions.relative_to(out_dir).as_posix(),
            "started_at": datetime.now(UTC).isoformat(),
        }
        state["attempts"].append(attempt)
        _persist_state(out_dir, state, manifest["n"])
        run_settings = settings.model_copy(update={"sessions_root": sessions.resolve(), "retention": "keep"})
        try:
            res = run_workflow(
                pdf,
                run_settings,
                understand=understand,
                review=True,
                export_dir=out_dir / "reports" / f"{number:04d}",
            )
            assert res.review is not None and res.exported_to is not None
            attempt.update(
                session_id=res.session_id,
                report=res.exported_to.relative_to(out_dir).as_posix(),
                variant_title_block=any(p.title_block_layout == "variant" for p in res.extraction.pages),
            )
            errors = []
            for name in ("checks", *LLM_REVIEWERS) if understand else ("checks",):
                output = ReviewerOutput.model_validate_json((res.exported_to / f"{name}.json").read_text())
                if output.error:
                    kind = output.error.split(":", 1)[0]
                    errors.append(kind if kind.isidentifier() and kind.endswith("Error") else "ReviewerError")
            if understand and (
                len(res.understanding) != res.extraction.n_pages
                or not all(r.valid for r in res.understanding)
            ):
                errors.append("InvalidUnderstanding")
            if errors:
                attempt.update(status="failed", errors=errors)
            else:
                if understand:
                    _validate_cached_reviewers(run_settings, res)
                rows = _record_rows(res, entry["path"], entry["sha256"])
                state["rows"].extend(rows)
                attempt.update(status="ok", errors=[], findings=len(rows))
        except Exception as exc:
            attempt.update(status="failed", errors=[type(exc).__name__])
        finally:
            _capture_calls(settings, out_dir, attempt)
            _persist_state(out_dir, state, manifest["n"])
            # Raw JSON evidence survives even when an exception prevented normal report export.
            for path in sessions.rglob("*.json"):
                target = out_dir / "attempt_evidence" / f"{number:04d}" / path.relative_to(sessions)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
            shutil.rmtree(sessions, ignore_errors=True)
        print(
            f"{number} attempts; {entry['path']}: {attempt['status']}; estimated run cost "
            f"${state['estimated_billed_usd']:.6f}",
            flush=True,
        )
        if attempt["status"] != "ok":
            break  # stop before multiplying a service/authentication/schema failure
    latest = {r["drawing"]: r for r in state["attempts"]}
    return [
        HeldoutRun(
            r["drawing"],
            out_dir / r["report"] if r.get("report") else None,
            r.get("findings", 0),
            r.get("cost_usd", 0),
            r.get("variant_title_block", False),
            ", ".join(r["errors"]) or None,
        )
        for r in latest.values()
    ]


def score_heldout(
    out: Path, labels: Path, *, engineer_confirmation: str = "", label_review_confirmation: str = ""
) -> dict[str, Any]:
    """Score raised findings separately by producer; AI-assisted draft labels never imply human validation."""
    predictions = out / "findings.csv"
    if not predictions.exists():
        predictions = out / "findings_unlabelled.csv"  # read historical CSVs without installing old drivers
    with predictions.open(encoding="utf-8-sig", newline="") as handle:
        originals = list(csv.DictReader(handle))
    with labels.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    state = json.loads((out / "run_state.json").read_text(encoding="utf-8"))
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    if state["manifest_sha256"] != _file_hash(out / "manifest.json") or state["rows_sha256"] != _hash(
        state["rows"]
    ):
        raise ValueError("original manifest or predictions changed")
    if originals != state["rows"]:
        raise ValueError("the prediction CSV differs from its immutable run ledger")
    history = state.get("attempts", state.get("runs", []))
    latest = {r.get("drawing", r.get("path")): r for r in history}
    expected = {e["path"] for e in manifest["drawings"]}
    if not set(latest) <= expected:
        raise ValueError("unexpected drawing in the run ledger")
    complete = set(latest) == expected and all(r["status"] == "ok" for r in latest.values())
    if bool(state.get("complete")) != complete:
        raise ValueError("run completion metadata does not match the drawing ledger")

    def key(row: dict[str, str]) -> str:
        return row.get("finding_key") or f"{row['drawing']}:{row['no']}"

    gold = {key(row): row for row in originals}
    if len(gold) != len(originals) or len(rows) != len(originals) or {key(row) for row in rows} != set(gold):
        raise ValueError("labels must cover every original finding exactly once")
    for row in rows:
        if any(
            row.get(col) != value
            for col, value in gold[key(row)].items()
            if col not in {"label", "label_reason", "labelled_by"}
        ):
            raise ValueError("a prediction column was edited")
        if (
            row.get("label", "").strip().lower() not in {"correct", "incorrect", "unsure"}
            or not row.get("label_reason", "").strip()
            or not row.get("labelled_by", "").strip()
        ):
            raise ValueError("each finding needs correct/incorrect/unsure, a reason and an actual labeler")
    if label_review_confirmation.strip() and any(
        "ai-assisted draft" in row["labelled_by"].lower() for row in rows
    ):
        raise ValueError(
            "AI-assisted draft labels require actual human review and attribution before confirmation"
        )

    def metrics(group: list[dict[str, str]]) -> dict[str, Any]:
        counts = Counter(r["label"].strip().lower() for r in group)
        correct, incorrect, unsure = (counts[k] for k in ("correct", "incorrect", "unsure"))
        decided, total = correct + incorrect, len(group)
        interval = None
        if decided:
            p, z = correct / decided, 1.959963984540054
            denominator = 1 + z * z / decided
            centre = (p + z * z / (2 * decided)) / denominator
            half = z * math.sqrt(p * (1 - p) / decided + z * z / (4 * decided**2)) / denominator
            interval = [max(0, centre - half), min(1, centre + half)]
        return {
            "findings": total,
            "correct": correct,
            "incorrect": incorrect,
            "unsure": unsure,
            "precision_decided": correct / decided if decided else None,
            "wilson_95": interval,
            "conservative_all_unsure_wrong": correct / total if total else None,
            "optimistic_all_unsure_right": (correct + unsure) / total if total else None,
        }

    confirmed = (
        complete
        and engineer_confirmation.strip()
        and label_review_confirmation.strip()
        and manifest.get("team_exclusions_note")
    )
    result = {
        "status": "final" if confirmed else "PROVISIONAL",
        "label_basis": "human review confirmed" if label_review_confirmation.strip() else "unconfirmed draft",
        "engineer_confirmation": engineer_confirmation,
        "label_review_confirmation": label_review_confirmation,
        "models": manifest["models"],
        "evaluation_kind": manifest.get("evaluation_kind", "native_heldout"),
        "decoder_version": manifest.get("decoder_version"),
        "completed_prediction_batch": complete,
        "planned_drawings": manifest["n"],
        "labels_sha256": _file_hash(labels),
        "estimated_billed_usd": state.get("estimated_billed_usd"),
        "provider_invoice_cost_usd": None,
        "groups": {
            "code_lookup": metrics([r for r in rows if not r["checked_by"].startswith("llm:")]),
            "ai_reviewers": metrics([r for r in rows if r["checked_by"].startswith("llm:")]),
        },
        "limits": "Raised-finding precision only; no recall measurement. Findings cluster by drawing; "
        "the Wilson interval assumes independence. Tiny AI denominators do not establish reliability. "
        "Registry-rate estimates are not invoices; unknown charges on failed calls are not invented.",
    }
    name = "metrics.json" if confirmed else "metrics_provisional.json"
    _save(out / name, result)
    return result
