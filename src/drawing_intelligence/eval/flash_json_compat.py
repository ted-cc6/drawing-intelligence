"""Audited decoding of Flash arrays; original responses and frozen runs remain untouched."""

from __future__ import annotations

import copy
import inspect
import json
import shutil
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from drawing_intelligence.eval import flash_restart as base
from drawing_intelligence.llm import LLMClient, LLMResponse
from drawing_intelligence.llm.client import Part
from drawing_intelligence.llm.registry import Role

DECODER_VERSION = "flash_findings_array_v1"


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def decode(text: str, schema: type[BaseModel] | None = None) -> tuple[dict[str, Any], str]:
    """Only wrap a findings array; never turn broken output into successful silence."""
    raw = json.loads(text)
    if isinstance(raw, list):
        payload, shape = {"findings": raw}, "array"
    elif isinstance(raw, dict):
        payload, shape = raw, "object"
    else:
        raise ValueError("reviewer response must be a findings object or array")
    if not isinstance(payload.get("findings"), list):
        raise ValueError("reviewer findings must be an array")
    if not all(isinstance(item, dict) for item in payload["findings"]):
        raise ValueError("every finding must be an object")
    if schema is not None:
        schema.model_validate(payload)
    return payload, shape


@contextmanager
def decoded_responses(out: Path, *, cache_only: bool):
    """Raw response caches stay byte-for-byte unchanged. Derived text exists only in memory."""
    original = LLMClient.complete
    events = []

    def complete(
        self: LLMClient,
        parts: list[Part],
        *,
        role: Role,
        node: str,
        model: str | None = None,
        thinking: str | None = None,
        schema: type[BaseModel] | None = None,
    ) -> LLMResponse:
        spec = self.registry.model(model, role)
        level = spec.thinking_level(thinking)
        req = self.build_request(spec, parts, schema, level)
        key = self.cache_key(req)
        if cache_only and (self.cache is None or self.cache.get(key) is None):
            raise ValueError("cached response missing; cache-only replay made no API call")
        response = original(self, parts, role=role, node=node, model=model, thinking=thinking, schema=schema)
        if role != "review" or spec.name != "qwen3.8-flash":
            return response
        event = {
            "cache_key": key,
            "node": node,
            "cached": response.cached,
            "raw_response_sha256": base.object_digest(response.text),
            "valid": False,
        }
        events.append(event)
        payload, shape = decode(response.text, schema)
        event.update(
            valid=True, raw_shape=shape, normalized_array=shape == "array", findings=len(payload["findings"])
        )
        return replace(response, text=json.dumps(payload, ensure_ascii=False))

    LLMClient.complete = complete
    try:
        yield
    finally:
        LLMClient.complete = original
        audit_path = out / "response_format_audit.json"
        prior = read(audit_path) if audit_path.exists() else {"decoder": DECODER_VERSION, "events": []}
        prior["events"].extend(events)
        unique = {e["cache_key"]: e for e in prior["events"]}
        prior["summary"] = {
            "unique_reviewer_responses": len(unique),
            "array_responses_normalized": sum(e.get("normalized_array", False) for e in unique.values()),
            "object_responses": sum(e.get("raw_shape") == "object" for e in unique.values()),
            "invalid_responses": sum(not e["valid"] for e in unique.values()),
        }
        base.dump(audit_path, prior)


def executor(*, stop_after: int | None = None):
    source = inspect.getsource(base.run_once)
    old = """                    payload = json.loads(response.get("text", ""))
                    if not isinstance(payload, dict) or not isinstance(payload.get("findings"), list):
                        raise ValueError("missing findings array")"""
    new = """                    decode(response.get("text", ""))"""
    marker = '    for entry in manifest["drawings"]:\n'
    if source.count(old) != 1 or source.count(marker) != 1:
        raise ValueError("Unexpected evaluator version; preserve the existing run.")
    changed = source.replace(old, new, 1).replace(
        marker,
        marker
        + '        if stop_after is not None and len(state["runs"]) >= stop_after:\n            break\n',
        1,
    )
    changed = changed.replace(
        "if billed(settings.telemetry_db) >= approved_soft_budget_usd:",
        "if stop_after is None and billed(settings.telemetry_db) >= approved_soft_budget_usd:",
        1,
    )  # A cache-only replay may run at the cap; the response wrapper blocks every API cache miss.
    namespace = {**vars(base), "decode": decode, "stop_after": stop_after}
    exec(compile(changed, str(Path(__file__)) + ":executor", "exec"), namespace)
    return namespace["run_once"], changed


def checked_state(out: Path) -> dict[str, Any] | None:
    path = out / "run_state.json"
    if not path.exists():
        return None
    state = read(path)
    if state["manifest_sha256"] != base.digest(out / "manifest.json"):
        raise ValueError("Saved manifest changed.")
    if state.get("rows_sha256") != base.object_digest(state["rows"]):
        raise ValueError("Saved prediction rows changed.")
    if state["runs"] and not (out / "runtime_data/telemetry.db").exists():
        raise ValueError("This run's cost ledger is missing.")
    return state


def prepare(root: Path, parent: Path, out: Path) -> dict[str, Any]:
    if parent.resolve() == out.resolve() or parent.resolve() in out.resolve().parents:
        raise ValueError("Use a separate sibling output folder for the decoder variant.")
    source_manifest = parent / "manifest.json"
    if not source_manifest.exists():
        source_manifest = out / "decoder_parent/manifest.json"
    original = read(source_manifest)
    if original["snapshot"] != base.snapshot(root):
        raise ValueError("Original source/config changed; keep the original frozen files.")
    if original["models"]["review"] != "qwen3.8-flash":
        raise ValueError("This compatibility decoder is for the Flash run.")
    parent_state = checked_state(parent) if (parent / "manifest.json").exists() else None
    parent_hash = base.digest(source_manifest)
    driver_hash = base.digest(Path(__file__))
    if (out / "manifest.json").exists():
        manifest = read(out / "manifest.json")
        if (
            manifest.get("parent_manifest_sha256") != parent_hash
            or manifest.get("decoder_driver_sha256") != driver_hash
            or manifest["drawings"] != original["drawings"]
        ):
            raise ValueError("Decoder protocol changed; preserve the existing variant.")
        checked_state(out)
        return manifest
    if out.exists() and any(out.iterdir()):
        raise ValueError("Variant folder is nonempty without a manifest.")
    out.mkdir(parents=True, exist_ok=True)
    provenance = out / "decoder_parent"
    provenance.mkdir()
    shutil.copyfile(source_manifest, provenance / "manifest.json")
    if (parent / "run_state.json").exists():
        shutil.copyfile(parent / "run_state.json", provenance / "run_state.json")
    for path in (parent / "reports").rglob("*.json"):
        target = provenance / "reports" / path.relative_to(parent / "reports")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    _, derived_source = executor()
    manifest = copy.deepcopy(original)
    manifest.update(
        created_at=datetime.now(UTC).isoformat(),
        decoder_version=DECODER_VERSION,
        evaluation_kind="fresh_flash_compatible_decoder",
        parent_run_name=parent.name,
        parent_manifest_sha256=parent_hash,
        decoder_driver_sha256=driver_hash,
        decoder_policy="Object or bare findings array; locally validate exact reviewer schema; "
        "preserve raw responses; no prompt/model/request changes.",
        parent_attempts=0 if parent_state is None else len(parent_state["runs"]),
        cost_note="The copied ledger contains the original run's charges plus this variant's new charges. "
        "Do not sum the two ledgers.",
    )
    for name in ("drawings.txt", "additional_exclusions.txt"):
        if (parent / name).exists():
            shutil.copyfile(parent / name, out / name)
    if (parent / "runtime_data/cache").exists():
        shutil.copytree(parent / "runtime_data/cache", out / "runtime_data/cache")
    old_db = parent / "runtime_data/telemetry.db"
    if old_db.exists():
        new_db = out / "runtime_data/telemetry.db"
        new_db.parent.mkdir(parents=True, exist_ok=True)
        with (
            closing(sqlite3.connect(old_db.as_uri() + "?mode=ro", uri=True)) as source,
            closing(sqlite3.connect(new_db)) as target,
        ):
            source.backup(target)
    base.dump(out / "decoder_protocol.json", {**manifest, "execution_source": derived_source})
    base.dump(out / "manifest.json", manifest)
    return manifest


def run(root: Path, parent: Path, out: Path, *, paid: bool = True) -> dict[str, Any] | None:
    parent, out = parent.resolve(), out.resolve()
    manifest = prepare(root, parent, out)
    state = checked_state(out)
    if state and any(r["status"] != "ok" for r in state["runs"]):
        print("A decoder-variant failure is retained; no automatic retries.")
        print([(r["path"], r["errors"]) for r in state["runs"] if r["status"] != "ok"])
        return state
    note = "User requested correction of the Flash array decoder; same sample and $2.50 cap."
    replay_target = manifest["parent_attempts"]
    done = 0 if state is None else len(state["runs"])
    if done < replay_target:
        print("Reprocessing existing attempts from saved responses only; API calls blocked.", flush=True)
        replay, _ = executor(stop_after=replay_target)
        with decoded_responses(out, cache_only=True):
            state = replay(root, out, approved_soft_budget_usd=2.5, approval_note=note)
        if any(r["status"] != "ok" for r in state["runs"]):
            print("Cache-only recovery stopped; no API calls made. Original results are preserved.")
            return state
        print("Cached attempts recovered without new API calls:", len(state["runs"]), flush=True)
    if paid and not (state and state.get("complete")):
        print("Continuing the same 24 drawings with the compatible decoder.", flush=True)
        execute, _ = executor()
        with decoded_responses(out, cache_only=False):
            state = execute(root, out, approved_soft_budget_usd=2.5, approval_note=note)
    if state:
        print("Successful:", sum(r["status"] == "ok" for r in state["runs"]), "/", manifest["n"])
        print("All planned drawings succeeded:", state.get("complete", False))
        print("Failures:", [(r["path"], r["errors"]) for r in state["runs"] if r["status"] != "ok"])
    print("[] means no issues raised; it does not mean all rules passed.")
    return state


def score(out: Path, labels: Path, *, confirmation: str = "") -> dict[str, Any]:
    result = base.score(out, labels, confirmation=confirmation)
    result.update(evaluation_kind="fresh_flash_compatible_decoder", decoder=DECODER_VERSION)
    audit = out / "response_format_audit.json"
    result["response_format_summary"] = read(audit)["summary"] if audit.exists() else {}
    result["cost_note"] = read(out / "manifest.json")["cost_note"]
    base.dump(out / "metrics.json", result)
    path = out / "README.md"
    path.write_text(
        path.read_text() + "\nDecoder: object or bare findings array, locally validated. "
        "Raw response format deviations are reported in response_format_audit.json.\n",
        encoding="utf-8",
    )
    return result
