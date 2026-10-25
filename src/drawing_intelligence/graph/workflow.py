"""The LangGraph review workflow (ADR 0001, ADR 0010): intake -> understand -> reviewers -> verify.

Nodes keep only file paths in the graph state: the artifacts themselves live in the session workspace, so
checkpoints stay small and everything is deleted with the workspace. The reviewers run in parallel; each
appends the path of its output to `reviewer_outputs`, and `verify` joins them.
"""

from __future__ import annotations

import json
import operator
import shutil
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Required, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from drawing_intelligence.extraction import EXTRACTION_FILE, ImagingConfig, extract_pdf, load_template
from drawing_intelligence.llm import LLMClient, load_registry
from drawing_intelligence.llm.client import CompletionFn, openai_completion
from drawing_intelligence.review import Rulebook, load_rulebook
from drawing_intelligence.review.checks import param_models
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.reference import load_reference
from drawing_intelligence.review.reviewers import BUILT_REVIEWERS, PLANNED_REVIEWERS
from drawing_intelligence.review.runner import run_checks
from drawing_intelligence.review.verify import verify
from drawing_intelligence.schemas import (
    DrawingKnowledge,
    Extraction,
    RejectedFinding,
    ReviewerOutput,
    ReviewResult,
    UnderstandingResult,
)
from drawing_intelligence.settings import Settings
from drawing_intelligence.storage import Session
from drawing_intelligence.understanding import understand_page


class WorkflowState(TypedDict, total=False):
    pdf_path: Required[str]
    template: str
    understand_model: str | None
    understand_thinking: str | None
    extraction_path: str
    understanding_paths: list[str]
    reviewer_outputs: Annotated[list[str], operator.add]  # parallel reviewers append, never overwrite
    review_result_path: str
    rejected_path: str


REVIEW_RESULT_FILE = "review_result.json"
REJECTED_FILE = "rejected.json"

# Reviewer name -> what it runs. LLM reviewers join here when they are built (ADR 0010).
ReviewerFn = Callable[[ReviewContext], ReviewerOutput]
REVIEWER_FNS: dict[str, ReviewerFn] = {"checks": run_checks}


@dataclass
class WorkflowResult:
    session_id: str
    extraction: Extraction
    understanding: list[UnderstandingResult] = field(default_factory=list)
    review: ReviewResult | None = None
    rejected: list[RejectedFinding] = field(default_factory=list)
    exported_to: Path | None = None


def _load_extraction(state: WorkflowState) -> Extraction:
    return Extraction.model_validate_json(Path(state.get("extraction_path", "")).read_text(encoding="utf-8"))


def _load_knowledge(state: WorkflowState) -> dict[int, DrawingKnowledge | None]:
    out: dict[int, DrawingKnowledge | None] = {}
    for p in state.get("understanding_paths", []):
        r = UnderstandingResult.model_validate_json(Path(p).read_text(encoding="utf-8"))
        out[r.page_number] = r.knowledge if r.valid else None
    return out


def skipped_reviewers(understand: bool) -> list[str]:
    """Planned reviewers that won't run: not built yet, or LLM reviewers without the understanding step."""
    run = [r for r in BUILT_REVIEWERS if r in REVIEWER_FNS and (understand or r == "checks")]
    return [r for r in PLANNED_REVIEWERS if r not in run]


def build_graph(
    session: Session,
    client: LLMClient | None,
    imaging: ImagingConfig | None = None,
    understand: bool = True,
    rulebook: Rulebook | None = None,
    reference: dict[str, Any] | None = None,
):
    """The workflow graph. With a rulebook, the review stage follows: reviewers in parallel, then verify.

    `reference` holds the lookup tables (config/reference) the lookup checks read.
    """
    ws = session.workspace

    def intake(state: WorkflowState) -> dict[str, Any]:  # nodes return partial state updates
        out = ws / "extraction"
        extract_pdf(Path(state["pdf_path"]), out, load_template(state.get("template", "wipro_pari")), imaging)
        session.heartbeat()
        return {"extraction_path": str(out / EXTRACTION_FILE)}

    def understand_node(state: WorkflowState) -> dict[str, Any]:
        assert client is not None
        ex_path = Path(state.get("extraction_path", ""))
        ex = Extraction.model_validate_json(ex_path.read_text(encoding="utf-8"))
        out = ws / "understanding"
        out.mkdir(exist_ok=True)
        paths = []
        for page in ex.pages:
            res = understand_page(
                client, page, ex_path.parent, state.get("understand_model"), state.get("understand_thinking")
            )
            p = out / f"page_{page.page_number}.json"
            p.write_text(res.model_dump_json(indent=1), encoding="utf-8")
            paths.append(str(p))
            session.heartbeat()
        return {"understanding_paths": paths}

    def reviewer_node(name: str, fn: ReviewerFn):
        def node(state: WorkflowState) -> dict[str, Any]:
            assert rulebook is not None
            out_dir = ws / "review"
            out_dir.mkdir(exist_ok=True)
            try:
                ctx = ReviewContext(
                    extraction=_load_extraction(state),
                    rulebook=rulebook,
                    template=load_template(state.get("template", "wipro_pari")),
                    knowledge=_load_knowledge(state),
                    reference=reference or {},
                )
                output = fn(ctx)
            except Exception as e:  # a crashed reviewer is reported, and the others still count
                output = ReviewerOutput(reviewer=name, error=f"{type(e).__name__}: {e}")
            path = out_dir / f"{name}.json"
            path.write_text(output.model_dump_json(indent=1), encoding="utf-8")
            session.heartbeat()
            return {"reviewer_outputs": [str(path)]}

        return node

    def verify_node(state: WorkflowState) -> dict[str, Any]:
        assert rulebook is not None
        outputs = [
            ReviewerOutput.model_validate_json(Path(p).read_text(encoding="utf-8"))
            for p in state.get("reviewer_outputs", [])
        ]
        result, rejected = verify(
            outputs, _load_extraction(state), rulebook, _load_knowledge(state), skipped_reviewers(understand)
        )
        out_dir = ws / "review"
        out_dir.mkdir(exist_ok=True)
        (out_dir / REVIEW_RESULT_FILE).write_text(result.model_dump_json(indent=1), encoding="utf-8")
        (out_dir / REJECTED_FILE).write_text(
            "[" + ",".join(r.model_dump_json() for r in rejected) + "]", encoding="utf-8"
        )
        return {
            "review_result_path": str(out_dir / REVIEW_RESULT_FILE),
            "rejected_path": str(out_dir / REJECTED_FILE),
        }

    g = StateGraph(WorkflowState)
    g.add_node("intake", intake)
    g.add_edge(START, "intake")
    last = "intake"
    if understand:
        g.add_node("understand", understand_node)
        g.add_edge("intake", "understand")
        last = "understand"
    if rulebook is None:
        g.add_edge(last, END)
        return g
    reviewers = [r for r in PLANNED_REVIEWERS if r not in skipped_reviewers(understand)]
    for name in reviewers:
        g.add_node(name, reviewer_node(name, REVIEWER_FNS[name]))
        g.add_edge(last, name)
    g.add_node("verify", verify_node)
    g.add_edge(reviewers, "verify")  # waits for every reviewer
    g.add_edge("verify", END)
    return g


def run_workflow(
    pdf_path: Path,
    settings: Settings,
    *,
    understand: bool = True,
    review: bool = False,
    model: str | None = None,
    thinking: str | None = None,
    imaging: ImagingConfig | None = None,
    export_dir: Path | None = None,
    completion_fn: CompletionFn = openai_completion,
) -> WorkflowResult:
    """Run one drawing through the workflow in its own session; with `review`, through to the verified review.

    Results are loaded into memory before the session closes. In ephemeral mode the workspace is then
    deleted; `export_dir` is the explicit way to keep a copy (with annotated images).
    """
    with Session(settings) as session:
        client = None
        if understand:
            client = LLMClient(
                load_registry(settings.config_path / "models.yaml"),
                settings,
                session.telemetry,
                session.cache,
                session.id,
                completion_fn,
            )
        rulebook = load_rulebook(settings.config_path / "rules", checks=param_models()) if review else None
        reference = load_reference(settings.config_path / "reference") if review else None
        conn = sqlite3.connect(session.checkpoint_db, check_same_thread=False)
        try:
            graph = build_graph(session, client, imaging, understand, rulebook, reference)
            app = graph.compile(checkpointer=SqliteSaver(conn))
            final = app.invoke(
                {
                    "pdf_path": str(pdf_path),
                    "understand_model": model,
                    "understand_thinking": thinking,
                },
                {"configurable": {"thread_id": session.id}},
            )
        finally:
            conn.close()  # must close before the workspace is deleted (Windows locks open files)

        ex_path = Path(final["extraction_path"])
        extraction = Extraction.model_validate_json(ex_path.read_text(encoding="utf-8"))
        results = [
            UnderstandingResult.model_validate_json(Path(p).read_text(encoding="utf-8"))
            for p in final.get("understanding_paths", [])
        ]
        review_result = None
        rejected: list[RejectedFinding] = []
        if "review_result_path" in final:
            review_result = ReviewResult.model_validate_json(
                Path(final["review_result_path"]).read_text(encoding="utf-8")
            )
            rejected = [
                RejectedFinding.model_validate(r)
                for r in json.loads(Path(final["rejected_path"]).read_text(encoding="utf-8"))
            ]
        session.n_pages = extraction.n_pages
        session.status = "ok" if all(r.valid for r in results) else "invalid_output"

        dest = export_dir / Path(pdf_path).stem if export_dir else None
        if dest is not None:
            _export(ex_path.parent, extraction, results, dest)
            for f in sorted((session.workspace / "review").glob("*.json")):  # no review dir -> nothing
                shutil.copyfile(f, dest / f.name)
        return WorkflowResult(session.id, extraction, results, review_result, rejected, dest)


def _export(ex_dir: Path, ex: Extraction, results: list[UnderstandingResult], dest: Path) -> None:
    from drawing_intelligence.viz import extraction_diagram, knowledge_overlay, symbol_gallery

    for f in ex_dir.rglob("*"):  # plain file copies: no permission bits (some mounts refuse chmod)
        if f.is_file():
            target = dest / f.relative_to(ex_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, target)
    by_page = {r.page_number: r for r in results}
    for page in ex.pages:
        if page.images is None:
            continue
        extraction_diagram(ex_dir, page).save(dest / f"page_{page.page_number}_extraction.png")
        res = by_page.get(page.page_number)
        if res is None:
            continue
        (dest / f"page_{page.page_number}_understanding.json").write_text(
            res.model_dump_json(indent=1), encoding="utf-8"
        )
        if res.knowledge:
            knowledge_overlay(ex_dir, page, res.knowledge).save(
                dest / f"page_{page.page_number}_knowledge.png"
            )
            gallery = symbol_gallery(ex_dir, page, res.knowledge)
            if gallery:
                gallery.save(dest / f"page_{page.page_number}_symbols.png")
