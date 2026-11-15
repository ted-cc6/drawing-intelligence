"""The web demo's run history and feedback analytics: kept in the server's memory, so a restart clears them.

A demo stand-in for the pilot's stored history (ADR 0012). Nothing about an upload is kept beyond its session:
callers list an upload as `UPLOAD_LABEL`, and a feedback row holds the rule and the decision, never the
drawing's text (a finding with no rule loses its model-written requirement). Visitors are anonymous browser
ids, numbered in the order they open a review (`visit`), not the order their reviews end.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

UPLOAD_LABEL = "Uploaded PDF"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _rate(accepted: int, decisions: int) -> float | None:
    return round(accepted / decisions, 3) if decisions else None


class Ledger:
    def __init__(self) -> None:
        self.since = _now()
        self._lock = threading.Lock()
        self._runs: dict[str, dict[str, Any]] = {}  # by session id, in the order the reviews ended
        self._feedback: dict[tuple[str, str], dict[str, Any]] = {}  # by (session id, finding id): latest wins
        self._visitors: dict[str, int] = {}

    def _visitor(self, visitor: str | None) -> None:
        if visitor and visitor not in self._visitors:
            self._visitors[visitor] = len(self._visitors) + 1

    def visit(self, visitor: str | None) -> None:
        """Number a visitor when they open a review: a slow upload started first stays Visitor 1."""
        with self._lock:
            self._visitor(visitor)

    def _label(self, visitor: str | None) -> str:
        return f"Visitor {self._visitors[visitor]}" if visitor in self._visitors else "Visitor ?"

    def record_run(
        self,
        *,
        session_id: str,
        visitor: str | None,
        drawing: str,
        mode: str,
        status: str,
        findings: int,
        fails: int,
        seconds: float | None,
        cost_usd: float,
        model: str | None,
        cached: bool,
    ) -> None:
        with self._lock:
            self._visitor(visitor)
            old = self._runs.get(session_id)
            self._runs[session_id] = {
                "no": old["no"] if old else len(self._runs) + 1,  # the row's key in the UI
                "session_id": session_id,
                "at": _now(),
                "visitor_id": visitor,
                "drawing": drawing,
                "mode": mode,
                "status": status,
                "findings": findings,
                "fails": fails,
                "seconds": seconds,
                "cost_usd": cost_usd,
                "qa_cost_usd": 0.0,
                "model": model,
                "cached": cached,
            }

    def add_qa_cost(self, session_id: str, usd: float) -> None:
        with self._lock:
            if session_id in self._runs:
                self._runs[session_id]["qa_cost_usd"] += usd

    def record_feedback(
        self,
        *,
        session_id: str,
        visitor: str | None,
        finding_id: str,
        rule_id: str | None,
        requirement: str | None,
        category: str,
        source: str,
        reviewer: str,
        result: str,
        decision: str,
    ) -> None:
        with self._lock:
            self._visitor(visitor)
            self._feedback[(session_id, finding_id)] = {
                "rule_id": rule_id,
                "requirement": requirement if rule_id else None,  # the rulebook's text only
                "category": category,
                "source": source,
                "reviewer": reviewer,
                "result": result,
                "decision": decision,
                "at": _now(),
            }

    def history(self, visitor: str | None) -> dict[str, Any]:
        """Every review since the server started, newest first, and cost and latency per model."""
        with self._lock:
            runs = [dict(r) for r in self._runs.values()]
            labels = {r["session_id"]: self._label(r["visitor_id"]) for r in runs}
            n_visitors = len(self._visitors)
        rows = []
        for r in reversed(runs):
            # a session id is the only key to another visitor's open session (one shared password): kept here
            vid, sid = r.pop("visitor_id"), r.pop("session_id")
            rows.append(r | {"visitor": labels[sid], "you": bool(visitor) and vid == visitor})
        by_model: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
        for r in runs:
            by_model[r["model"]].append(r)
        models = []
        for model, rs in by_model.items():
            live = [r for r in rs if not r["cached"]]
            timed = [r for r in live if r["status"] == "done"]
            models.append(
                {
                    "model": model,
                    "runs": len(rs),
                    "live_runs": len(live),
                    "avg_live_seconds": (
                        round(sum(r["seconds"] or 0 for r in timed) / len(timed), 1) if timed else None
                    ),
                    "avg_live_cost_usd": round(sum(r["cost_usd"] for r in timed) / len(timed), 4)
                    if timed
                    else None,
                    "total_cost_usd": round(sum(r["cost_usd"] for r in rs), 4),
                    "qa_cost_usd": round(sum(r["qa_cost_usd"] for r in rs), 4),
                }
            )
        return {"since": self.since, "runs": rows, "models": models, "visitors": n_visitors}

    def feedback_summary(self) -> dict[str, Any]:
        """Accept/reject counts overall, by source, by reviewer and by rule (most rejected first)."""
        with self._lock:
            rows = [dict(r) for r in self._feedback.values()]

        def group(key: str) -> list[dict[str, Any]]:
            out: dict[str, dict[str, Any]] = {}
            for r in rows:
                g = out.setdefault(r[key], {key: r[key], "decisions": 0, "accepted": 0})
                g["decisions"] += 1
                g["accepted"] += r["decision"] == "accept"
            return [g | {"rate": _rate(g["accepted"], g["decisions"])} for g in out.values()]

        rules: dict[str, dict[str, Any]] = {}
        for r in rows:
            if not r["rule_id"]:
                continue
            g = rules.setdefault(
                r["rule_id"],
                {
                    "rule_id": r["rule_id"],
                    "requirement": r["requirement"],
                    "source": r["source"],
                    "decisions": 0,
                    "accepted": 0,
                    "rejected": 0,
                },
            )
            g["decisions"] += 1
            g["accepted" if r["decision"] == "accept" else "rejected"] += 1
        by_rule = sorted(rules.values(), key=lambda g: (-g["rejected"], -g["decisions"], g["rule_id"]))
        accepted = sum(r["decision"] == "accept" for r in rows)
        return {
            "since": self.since,
            "decisions": len(rows),
            "accepted": accepted,
            "rejected": len(rows) - accepted,
            "by_source": group("source"),
            "by_reviewer": group("reviewer"),
            "by_rule": [g | {"rate": _rate(g["accepted"], g["decisions"])} for g in by_rule],
        }
