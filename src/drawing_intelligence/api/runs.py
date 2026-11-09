"""Review runs for the web demo: one `DemoSession` per opened drawing, held in memory by the `SessionStore`.

A run calls the same `run_workflow` the CLI uses, in a worker thread, with its outputs exported into the
session's own folder (so the sheet image, the Excel report and the annotated PNG can be served). The folder is
deleted when the session ends or goes idle, as ADR 0003 asks of every session.
"""

from __future__ import annotations

import shutil
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from drawing_intelligence.graph import WorkflowResult, run_workflow
from drawing_intelligence.llm.client import CompletionFn, openai_completion
from drawing_intelligence.qa.agent import Answer, Conversation
from drawing_intelligence.qa.data import DrawingData
from drawing_intelligence.qa.session import AskSession
from drawing_intelligence.review.reviewers import LLM_REVIEWERS, PLANNED_REVIEWERS
from drawing_intelligence.schemas import FindingFeedback
from drawing_intelligence.settings import Settings

# The stage bar: (key, label, the graph nodes that finish it).
STAGES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("intake", "Intake", ("intake",)),
    ("understand", "Understand", ("understand",)),
    ("reviewers", "Review", PLANNED_REVIEWERS),
    ("verify", "Verify", ("verify",)),
    ("report", "Report", ("report",)),
)


class Cancelled(Exception):
    """The session was closed while its review was still running."""


@dataclass
class Stage:
    key: str
    label: str
    nodes: tuple[str, ...]
    status: str = "pending"  # pending | running | done | skipped | error
    started: float | None = None
    finished: float | None = None
    done_nodes: set[str] = field(default_factory=set)

    @property
    def seconds(self) -> float | None:
        if self.started is None:
            return None
        return round((self.finished or time.monotonic()) - self.started, 1)


@dataclass
class DemoSession:
    id: str
    name: str
    pdf: Path
    folder: Path
    demo_id: str | None
    live: bool  # an upload, whose replies are probably not cached
    status: str = "queued"  # queued | running | done | error | cancelled
    error: str | None = None
    created: float = field(default_factory=time.time)
    touched: float = field(default_factory=time.time)
    stages: list[Stage] = field(default_factory=list)
    started: float | None = None
    finished: float | None = None
    result: WorkflowResult | None = None
    data: DrawingData | None = None
    feedback: dict[str, FindingFeedback] = field(default_factory=dict)
    ask: AskSession | None = None
    conversation: Conversation | None = None
    qa_cost: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)
    expected_nodes: set[str] = field(default_factory=set)  # the graph nodes this run will report
    sheets: dict[int, tuple[float, int, int]] = field(default_factory=dict)  # page -> (pts->px, w, h)
    cancelled: threading.Event = field(default_factory=threading.Event)  # set when the user closes it

    @property
    def out_dir(self) -> Path:
        """Where the workflow exported this drawing's outputs (extraction, images, report)."""
        return self.folder / "out" / self.pdf.stem

    def on_progress(self, node: str) -> None:
        if self.cancelled.is_set():
            raise Cancelled  # stops the graph before its next node; a model call already sent still finishes
        now = time.monotonic()
        for i, st in enumerate(self.stages):
            if node not in st.nodes or st.status in ("done", "skipped"):
                continue
            st.done_nodes.add(node)
            if st.started is None:
                st.started = now
            if st.done_nodes >= {n for n in st.nodes if n in self.expected_nodes}:
                st.status, st.finished = "done", now
                for nxt in self.stages[i + 1 :]:
                    if nxt.status == "pending":
                        nxt.status, nxt.started = "running", now
                        break
            return

    def billed(self) -> float:
        if self.result is None:
            return 0.0
        review = self.result.review.cost_usd if self.result.review else 0.0
        return review + sum(r.cost_usd for r in self.result.understanding if not r.cached)

    def cached(self) -> bool:
        return self.result is not None and all(r.cached for r in self.result.understanding)


class SessionStore:
    """All open demo sessions. Thread-safe enough for one small server: one lock around the dictionary."""

    def __init__(
        self,
        settings: Settings,
        root: Path | None = None,
        idle_s: float = 2 * 3600,
        max_live: int = 30,
        completion_fn: CompletionFn = openai_completion,
    ):
        self.settings = settings
        self.completion_fn = completion_fn  # tests pass a fake, so a cache miss never reaches a provider
        self.root = root or Path(tempfile.mkdtemp(prefix="di-web-"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.idle_s = idle_s
        self.live_left = max_live
        self._sessions: dict[str, DemoSession] = {}
        self._lock = threading.Lock()
        # Two lanes: live uploads take minutes, demo replays seconds; a demo never waits behind uploads.
        self._live_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="di-live")
        self._demo_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="di-demo")

    # --- lifecycle ------------------------------------------------------------------------------------------

    def create(self, pdf: Path, name: str, demo_id: str | None, live: bool) -> DemoSession:
        sid = uuid.uuid4().hex[:12]
        folder = self.root / sid
        folder.mkdir(parents=True)
        local = folder / ("input" + pdf.suffix.lower())
        shutil.copyfile(pdf, local)  # plain copy: some mounts refuse permission bits
        sess = DemoSession(sid, name, local, folder, demo_id, live)
        sess.stages = [Stage(k, label, nodes) for k, label, nodes in STAGES]
        with self._lock:
            self._sessions[sid] = sess
        (self._live_pool if live else self._demo_pool).submit(self._run, sess)
        return sess

    def get(self, sid: str) -> DemoSession | None:
        self.sweep()
        with self._lock:
            sess = self._sessions.get(sid)
        if sess is not None:
            sess.touched = time.time()
        return sess

    def delete(self, sid: str) -> bool:
        with self._lock:
            sess = self._sessions.pop(sid, None)
        if sess is None:
            return False
        self._close(sess)
        return True

    def sweep(self) -> None:
        """End sessions nobody has looked at for `idle_s` (the idle timeout of PROJECT.md §7)."""
        cutoff = time.time() - self.idle_s
        with self._lock:
            idle = [s for s in self._sessions.values() if s.touched < cutoff and s.status != "running"]
            for s in idle:
                del self._sessions[s.id]
        for s in idle:
            self._close(s)

    def shutdown(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for s in sessions:
            self._close(s)
        for pool in (self._live_pool, self._demo_pool):
            pool.shutdown(wait=False, cancel_futures=True)

    def _close(self, sess: DemoSession) -> None:
        sess.cancelled.set()  # a queued run is skipped, a running one stops at its next node
        with sess.lock:
            if sess.ask is not None:
                sess.ask.__exit__(None, None, None)
                sess.ask = sess.conversation = None
        shutil.rmtree(sess.folder, ignore_errors=True)

    # --- the run --------------------------------------------------------------------------------------------

    def _run(self, sess: DemoSession) -> None:
        if sess.cancelled.is_set():
            return  # closed while it waited in the queue: no work, no model calls
        # "keep" turns on the shared response cache (ephemeral runs never read it); the workspace still goes
        # when the session ends, because it lives inside the session folder.
        run_settings = self.settings.model_copy(
            update={"sessions_root": sess.folder / "workspace", "retention": "keep"}
        )
        understand = True
        sess.expected_nodes = {"intake", "understand", "verify", "report", *PLANNED_REVIEWERS}
        if not understand:
            sess.expected_nodes -= {"understand", *LLM_REVIEWERS}
        sess.status, sess.started = "running", time.monotonic()
        sess.stages[0].status, sess.stages[0].started = "running", sess.started
        try:
            sess.result = run_workflow(
                sess.pdf,
                run_settings,
                understand=understand,
                review=True,
                export_dir=sess.folder / "out",
                progress=sess.on_progress,
                completion_fn=self.completion_fn,
            )
            assert sess.result.review is not None
            knowledge = {r.page_number: r.knowledge for r in sess.result.understanding}
            sess.data = DrawingData.build(
                sess.result.extraction, knowledge, sess.result.review, self.settings
            )
            sess.status = "done"
        except Exception as e:  # shown in the UI; the session stays open so the user can read the error
            if isinstance(e, Cancelled) or sess.cancelled.is_set():
                sess.status = "cancelled"  # nobody is looking: a failure after the close is not an error
            else:
                sess.status, sess.error = "error", f"{type(e).__name__}: {e}"
            for st in sess.stages:
                if st.status == "running":
                    st.status = "error"
        finally:
            sess.finished = time.monotonic()
            for st in sess.stages:
                if st.status == "running":
                    st.status, st.finished = ("done" if sess.status == "done" else "error"), sess.finished
            if sess.cancelled.is_set():
                shutil.rmtree(sess.folder, ignore_errors=True)  # the run may have written after the close

    # --- Q&A ------------------------------------------------------------------------------------------------

    def ask(self, sess: DemoSession, question: str) -> Answer:
        assert sess.data is not None
        with sess.lock:
            if sess.conversation is None:
                qa_settings = self.settings.model_copy(update={"sessions_root": sess.folder / "qa"})
                sess.ask = AskSession(qa_settings, keep=False).__enter__()
                sess.conversation = sess.ask.conversation(sess.data)
            answer = sess.conversation.ask(question)
            sess.qa_cost += answer.cost_usd
            return answer

    def record_feedback(self, sess: DemoSession, fb: FindingFeedback) -> None:
        sess.feedback[fb.finding_id] = fb
        log = self.settings.feedback_log
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as fh:
            fh.write(fb.model_dump_json() + "\n")

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"open_sessions": len(self._sessions), "live_runs_left": self.live_left}
