"""Q&A sessions for `di ask` (ADR 0011): review the drawing, then talk about it in a session workspace.

The review runs (or replays from the shared response cache) in a throwaway workflow session. The conversation
gets its own session: its workspace holds the drawing's saved results and the history, and is deleted when the
conversation ends unless it is kept, so `di ask --session <id>` can reopen it.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from drawing_intelligence.llm import LLMClient, load_registry
from drawing_intelligence.qa.agent import Conversation, Limits
from drawing_intelligence.qa.data import DrawingData
from drawing_intelligence.settings import Settings
from drawing_intelligence.storage import ResponseCache
from drawing_intelligence.storage.session import Session


def review_drawing(
    pdf: Path, settings: Settings, *, understand: bool = True, llm_review: bool = True
) -> tuple[DrawingData, float]:
    """The drawing's saved results, and what producing them was billed (0 when replayed from the cache)."""
    from drawing_intelligence.graph import run_workflow

    tmp = Path(tempfile.mkdtemp(prefix="di-ask-"))
    run_settings = settings.model_copy(update={"sessions_root": tmp, "retention": "keep"})  # shared cache
    try:
        res = run_workflow(pdf, run_settings, understand=understand, review=True, llm_review=llm_review)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    assert res.review is not None
    billed = res.review.cost_usd + sum(r.cost_usd for r in res.understanding if not r.cached)
    knowledge = {r.page_number: r.knowledge for r in res.understanding}
    return DrawingData.build(res.extraction, knowledge, res.review, settings), billed


class AskSession:
    """One conversation's session. Use as a context manager; `keep` decides whether the workspace survives."""

    def __init__(self, settings: Settings, session_id: str | None = None, keep: bool = False):
        self.settings = settings.model_copy(update={"retention": "keep"})  # the shared response cache
        self.session = Session(self.settings, session_id)
        self.keep = keep

    @property
    def id(self) -> str:
        return self.session.id

    @property
    def folder(self) -> Path:
        return self.session.workspace / "qa"

    def __enter__(self) -> AskSession:
        self.session.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.session.close("ok")
        if not self.keep:
            shutil.rmtree(self.session.workspace, ignore_errors=True)

    def conversation(self, data: DrawingData, model: str | None = None) -> Conversation:
        s = self.settings
        registry = load_registry(s.config_path / "models.yaml")
        client = LLMClient(registry, s, self.session.telemetry, ResponseCache(s.cache_dir), self.id)
        limits = Limits(s.qa_max_tool_calls, s.qa_max_regenerations, s.qa_max_cost_usd)
        conv = Conversation(data, client, model=model, limits=limits, feedback_path=s.feedback_log)
        history = self.folder / "history.json"
        if history.exists():
            conv.history = json.loads(history.read_text(encoding="utf-8"))
            for m in conv.history:
                conv.corpus.add(str(m.get("content") or ""))
        return conv

    def save(self, conv: Conversation) -> None:
        conv.data.save(self.folder)
        (self.folder / "history.json").write_text(
            json.dumps(conv.history, ensure_ascii=False), encoding="utf-8"
        )

    def load(self) -> DrawingData:
        if not (self.folder / "extraction.json").exists():
            raise FileNotFoundError(f"session {self.id} has no saved Q&A data (was it kept with --keep?)")
        return DrawingData.load(self.folder, self.settings)
