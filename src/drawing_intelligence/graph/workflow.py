"""The LangGraph review workflow. Built today: intake -> understand (ADR 0001).

Nodes keep only file paths in the graph state: the artifacts themselves live in the session workspace, so
checkpoints stay small and everything is deleted with the workspace.
"""

from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Required, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from drawing_intelligence.extraction import EXTRACTION_FILE, ImagingConfig, extract_pdf, load_template
from drawing_intelligence.llm import LLMClient, load_registry
from drawing_intelligence.llm.client import CompletionFn, openai_completion
from drawing_intelligence.schemas import Extraction, UnderstandingResult
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


@dataclass
class WorkflowResult:
    session_id: str
    extraction: Extraction
    understanding: list[UnderstandingResult] = field(default_factory=list)
    exported_to: Path | None = None


def build_graph(
    session: Session,
    client: LLMClient | None,
    imaging: ImagingConfig | None = None,
    understand: bool = True,
):
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

    g = StateGraph(WorkflowState)
    g.add_node("intake", intake)
    g.add_edge(START, "intake")
    if understand:
        g.add_node("understand", understand_node)
        g.add_edge("intake", "understand")
        g.add_edge("understand", END)
    else:
        g.add_edge("intake", END)
    return g


def run_workflow(
    pdf_path: Path,
    settings: Settings,
    *,
    understand: bool = True,
    model: str | None = None,
    thinking: str | None = None,
    imaging: ImagingConfig | None = None,
    export_dir: Path | None = None,
    completion_fn: CompletionFn = openai_completion,
) -> WorkflowResult:
    """Run one drawing through the workflow in its own session.

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
        conn = sqlite3.connect(session.checkpoint_db, check_same_thread=False)
        try:
            app = build_graph(session, client, imaging, understand).compile(checkpointer=SqliteSaver(conn))
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
        session.n_pages = extraction.n_pages
        session.status = "ok" if all(r.valid for r in results) else "invalid_output"

        if export_dir is not None:
            _export(ex_path.parent, extraction, results, export_dir / Path(pdf_path).stem)
        return WorkflowResult(
            session.id, extraction, results, export_dir / Path(pdf_path).stem if export_dir else None
        )


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
