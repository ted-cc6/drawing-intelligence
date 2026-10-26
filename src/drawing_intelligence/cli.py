"""The `di` command line. Every command works the same on Windows, macOS and Linux."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from drawing_intelligence import __version__
from drawing_intelligence.settings import get_settings

app = typer.Typer(
    help="Drawing Intelligence: agentic AI review of 2D engineering drawings.", no_args_is_help=True
)
eval_app = typer.Typer(help="Evaluate extraction, understanding and review.", no_args_is_help=True)
app.add_typer(eval_app, name="eval")
console = Console()

ModelOpt = Annotated[str | None, typer.Option("--model", "-m", help="registered model (see `di models`)")]
ThinkingOpt = Annotated[str | None, typer.Option("--thinking", "-t", help="thinking option of that model")]
ExportOpt = Annotated[
    Path | None, typer.Option("--export", help="keep a copy of the outputs and annotated images here")
]
NoUnderstandOpt = Annotated[
    bool, typer.Option("--no-understand", help="skip the LLM step: code checks on the exact PDF text only")
]
NoLlmReviewOpt = Annotated[
    bool, typer.Option("--no-llm-review", help="understand, but run only the code checks")
]
ReviewModelOpt = Annotated[str | None, typer.Option("--review-model", help="model for the LLM reviewers")]
ReviewThinkingOpt = Annotated[str | None, typer.Option("--review-thinking", help="their thinking option")]


def _money(v: float) -> str:
    return f"${v:.3f}"


@app.callback()
def main() -> None:
    """Drawing Intelligence: agentic AI review of 2D engineering drawings."""


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.command()
def models() -> None:
    """Registered models: roles, prices, thinking options. Warns about stale prices."""
    from drawing_intelligence.llm import load_registry
    from drawing_intelligence.llm.registry import PRICE_STALE_AFTER_DAYS

    s = get_settings()
    reg = load_registry(s.config_path / "models.yaml")
    t = Table(title="Model registry (config/models.yaml)")
    for col in ("model", "provider", "roles", "$/M in", "$/M out", "thinking", "price checked", "key"):
        t.add_column(col, no_wrap=col == "model")
    for name, m in reg.models.items():
        p = reg.provider(m)
        age = m.price.age_days()
        checked = f"{m.price.verified_on} ({age} d)" + (" ⚠ stale" if age > PRICE_STALE_AFTER_DAYS else "")
        thinking = ", ".join(f"[b]{o}[/b]" if o == m.thinking.default else o for o in m.thinking.options)
        t.add_row(
            name,
            p.label,
            ", ".join(m.roles),
            f"{m.price.input_per_mtok:g}",
            f"{m.price.output_per_mtok:g}",
            thinking,
            checked,
            "✓" if s.api_key(p.api_key_env) else "[red]missing[/red]",
        )
    console.print(t)
    console.print("Role defaults: " + ", ".join(f"{r} → {n}" for r, n in reg.defaults.items()))
    console.print("Bold = the model's default thinking option.")


@app.command()
def rules(
    folder: Annotated[Path | None, typer.Argument(help="rules folder (default config/rules)")] = None,
) -> None:
    """Validate the rulebook and summarise it: rules per category, check type, built checks and status."""
    from collections import Counter

    from drawing_intelligence.review import RulebookError, load_rulebook
    from drawing_intelligence.review.checks import param_models
    from drawing_intelligence.review.reference import ReferenceTableError, load_reference
    from drawing_intelligence.schemas.review import CATEGORY_LABELS

    checks = param_models()
    try:
        book = load_rulebook(folder, checks=checks)
        tables = load_reference(folder.parent / "reference" if folder else None)
    except (RulebookError, ReferenceTableError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e
    if not book.rules:
        console.print("The rulebook is empty: add rules in config/rules/*.yaml (see config/rules/README.md).")
        return
    t = Table(title=f"Rulebook {book.version} ({len(book.rules)} rules)")
    for col in ("category", "rules", "code", "lookup", "llm", "check built", "client confirmed"):
        t.add_column(col)
    by_cat: dict[str, Counter] = {}
    for r in book.rules:
        c = by_cat.setdefault(r.category, Counter())
        c["rules"] += 1
        c[r.check_type] += 1
        c["built"] += r.check in checks
        c["confirmed"] += r.status == "client_confirmed"
    for cat, c in by_cat.items():
        t.add_row(
            CATEGORY_LABELS[cat],
            *(str(c[k]) for k in ("rules", "code", "lookup", "llm", "built", "confirmed")),
        )
    console.print(t)
    built = sum(c["built"] for c in by_cat.values())
    console.print(
        f"{built} rules have a built check ({len(checks)} check functions); "
        f"{len(book.not_built(checks))} code/lookup rules are not built yet and report not_checked. "
        "LLM rules run in the LLM reviewers."
    )
    console.print(f"Reference tables: {', '.join(sorted(tables)) or 'none'}.")


def _print_extraction(ex) -> None:
    for p in ex.pages:
        console.rule(
            f"{ex.source_file} · page {p.page_number} · {p.page_size_pts[0]:.0f}x{p.page_size_pts[1]:.0f} pt"
        )
        console.print(
            f"dimensions {len(p.dimensions)} · view labels {len(p.view_labels)} · notes {len(p.notes)} · "
            f"title-block lines {len(p.title_block_text)} · matched lines {len(p.matched_lines)}"
        )
        if p.chain_checks:
            t = Table("chain", "sum", "overall", "diff", "consistent?")
            for c in p.chain_checks:
                ok = "[green]yes[/green]" if c.match else "[red]MISMATCH[/red]"
                t.add_row(" + ".join(c.chain_texts), f"{c.chain_sum:g}", c.overall_text, f"{c.diff:g}", ok)
            console.print(t)
        for w in p.warnings:
            console.print(f"[yellow]warning:[/yellow] {w}")
    for w in ex.warnings:
        console.print(f"[yellow]warning:[/yellow] {w}")


@app.command()
def extract(pdf: Path, export: ExportOpt = None) -> None:
    """Stage 1 only: exact text, dimensions and chain checks. No API cost."""
    from drawing_intelligence.graph import run_workflow

    res = run_workflow(pdf, get_settings(), understand=False, export_dir=export)
    _print_extraction(res.extraction)
    _footer(res)


@app.command()
def run(pdf: Path, model: ModelOpt = None, thinking: ThinkingOpt = None, export: ExportOpt = None) -> None:
    """Run the workflow (intake → understand) on one drawing in a fresh session."""
    from drawing_intelligence.graph import run_workflow

    res = run_workflow(pdf, get_settings(), model=model, thinking=thinking, export_dir=export)
    _print_extraction(res.extraction)
    t = Table(title="Understanding")
    for col in (
        "page",
        "model",
        "thinking",
        "valid",
        "dims",
        "symbols",
        "tokens in/out",
        "cost",
        "time",
        "cached",
    ):
        t.add_column(col)
    for r in res.understanding:
        k = r.knowledge
        t.add_row(
            str(r.page_number),
            r.model,
            r.thinking,
            "[green]yes[/green]" if r.valid else "[red]no[/red]",
            str(len(k.dimensions)) if k else "-",
            str(len(k.symbols)) if k else "-",
            f"{r.input_tokens:,} / {r.output_tokens:,}",
            _money(r.cost_usd),
            f"{r.latency_s:.0f} s",
            "yes" if r.cached else "no",
        )
    console.print(t)
    for r in res.understanding:
        for p in r.problems:
            console.print(f"[yellow]page {r.page_number}:[/yellow] {p}")
    _footer(res)


_STATUS_ORDER = ("fail", "warning", "pass", "not_applicable", "not_checked")
_SEVERITY_STYLE = {"critical": "bold red", "major": "red", "minor": "yellow", "info": "dim"}


def _location(f) -> str:
    return "; ".join(f"p{e.page} {e.ref or e.quote or e.kind}" for e in f.evidence)


def _print_review(review, rejected) -> None:
    from collections import Counter

    t = Table(title=f"Review of {review.source_file} (rulebook {review.rulebook_version})")
    for col in ("severity", "result", "rule", "category", "comment", "location"):
        t.add_column(col, overflow="fold")
    for f in review.by_severity():
        style = _SEVERITY_STYLE[f.severity]
        t.add_row(
            f"[{style}]{f.severity}[/{style}]",
            f.result,
            f.rule_id or "-",
            f.category,
            f.comment,
            _location(f),
        )
    console.print(t if review.findings else "No findings.")
    counts = Counter(s.status for s in review.rule_statuses)
    parts = [f"{counts[k]} {k.replace('_', ' ')}" for k in _STATUS_ORDER if counts[k]]
    console.print(f"{len(review.rule_statuses)} rules: " + " · ".join(parts))
    console.print(
        f"Reviewers run: {', '.join(review.reviewers_run) or 'none'}; "
        f"skipped: {', '.join(review.reviewers_skipped) or 'none'}. "
        f"Review cost {_money(review.cost_usd)}, {review.latency_s:.1f} s."
    )
    if rejected:
        console.print(f"[yellow]{len(rejected)} finding(s) dropped by verify:[/yellow]")
        for r in rejected:
            console.print(f"  {r.finding.rule_id}: {r.reason} - {r.detail}")


@app.command()
def review(
    pdf: Path,
    model: ModelOpt = None,
    thinking: ThinkingOpt = None,
    export: ExportOpt = None,
    no_understand: NoUnderstandOpt = False,
    no_llm_review: NoLlmReviewOpt = False,
    review_model: ReviewModelOpt = None,
    review_thinking: ReviewThinkingOpt = None,
) -> None:
    """Review one drawing against the rulebook: intake → understand → reviewers → verify."""
    from drawing_intelligence.graph import run_workflow

    res = run_workflow(
        pdf,
        get_settings(),
        understand=not no_understand,
        review=True,
        llm_review=not no_llm_review,
        model=model,
        thinking=thinking,
        review_model=review_model,
        review_thinking=review_thinking,
        export_dir=export,
    )
    understanding_cost = sum(r.cost_usd for r in res.understanding)
    if res.understanding:
        console.print(f"Understanding: {_money(understanding_cost)} ({res.understanding[0].model})")
    assert res.review is not None
    _print_review(res.review, res.rejected)
    if res.exported_to:
        console.print(f"Report: {res.exported_to / 'review_report.xlsx'} and page_*_review.png")
    else:
        console.print("Add --export DIR to keep the Excel report and the annotated sheet.")
    _footer(res)


@app.command()
def ask(
    pdf: Annotated[Path | None, typer.Argument(help="the drawing; reviewed first (free if cached)")] = None,
    question: Annotated[
        str | None, typer.Option("--question", "-q", help="ask one question and exit")
    ] = None,
    session_id: Annotated[str | None, typer.Option("--session", help="reopen a kept conversation")] = None,
    keep: Annotated[
        bool, typer.Option("--keep", help="keep the conversation to reopen with --session")
    ] = False,
    model: ModelOpt = None,
    no_understand: NoUnderstandOpt = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="show the tool calls")] = False,
) -> None:
    """Ask questions about a reviewed drawing; answers cite the drawing's data (ADR 0011)."""
    from drawing_intelligence.qa.session import AskSession, review_drawing

    s = get_settings()
    if (pdf is None) == (session_id is None):
        raise typer.BadParameter("give a drawing PDF or --session ID, not both")
    with AskSession(s, session_id, keep=keep or session_id is not None) as sess:
        if pdf is not None:
            console.print(f"Reviewing {pdf.name} ...")
            data, billed = review_drawing(pdf, s, understand=not no_understand)
            console.print(f"Reviewed: {len(data.findings)} findings (review billed {_money(billed)}).")
        else:
            data = sess.load()
        conv = sess.conversation(data, model)
        questions = [question] if question else None
        if questions is None:
            console.print(
                "Ask about the drawing, its findings, the rules or the standard tables. Empty line ends."
            )
        total = 0.0
        while True:
            q = questions.pop(0) if questions else (None if question else console.input("[bold]?[/] "))
            if not q or not q.strip():
                break
            ans = conv.ask(q.strip())
            total += ans.cost_usd
            if verbose and ans.tool_calls:
                console.print(f"[dim]tools: {', '.join(ans.tool_calls)}[/]")
            console.print(ans.display(), markup=False)
            console.print(f"[dim]{'verified' if ans.verified else 'NOT verified'}; {_money(ans.cost_usd)}[/]")
        if sess.keep:
            sess.save(conv)
            console.print(f"Conversation kept: di ask --session {sess.id}")
        console.print(f"Q&A billed {_money(total)}.")


def _footer(res) -> None:
    s = get_settings()
    if res.exported_to:
        console.print(f"Outputs exported to {res.exported_to}")
    if s.retention == "ephemeral":
        console.print(f"Session {res.session_id} closed; its workspace was deleted (DI_RETENTION=ephemeral).")
    else:
        console.print(f"Session {res.session_id}: workspace kept in {s.sessions_dir / res.session_id}")


@app.command()
def telemetry() -> None:
    """Average cost and latency per model, thinking option and node (from content-free telemetry)."""
    from drawing_intelligence.storage import Telemetry

    rows = Telemetry(get_settings().telemetry_db).model_summary()
    t = Table(title="LLM calls (excluding cache hits and errors)")
    for col in (
        "model",
        "thinking",
        "node",
        "calls",
        "avg latency",
        "avg cost",
        "avg tokens in/out",
        "total",
    ):
        t.add_column(col)
    for r in rows:
        t.add_row(
            r["model"],
            r["thinking"],
            r["node"],
            str(r["calls"]),
            f"{r['avg_latency_s']:.0f} s",
            _money(r["avg_cost_usd"]),
            f"{r['avg_input_tokens']:,.0f} / {r['avg_output_tokens']:,.0f}",
            _money(r["total_cost_usd"]),
        )
    console.print(t if rows else "No LLM calls recorded yet.")


# ---------------------------------------------------------------------------------------------- eval


def _pdfs(folder: Path | None) -> list[Path]:
    folder = folder or get_settings().raw_dir
    pdfs = sorted(folder.glob("*.pdf"))
    if not pdfs:
        raise typer.BadParameter(f"no PDFs in {folder}")
    return pdfs


@eval_app.command("baseline")
def eval_baseline(
    folder: Annotated[Path | None, typer.Argument(help="PDF folder (default data/raw)")] = None,
) -> None:
    """Diff new extraction outputs against the original notebook's saved outputs."""
    from drawing_intelligence.eval.baseline import diff_page, load_baseline
    from drawing_intelligence.extraction import extract_pdf

    s = get_settings()
    t = Table(title="Extraction vs notebook baseline (page 1)")
    for col in ("drawing", "section", "baseline", "new", "only in baseline", "only in new"):
        t.add_column(col)
    for pdf in _pdfs(folder):
        base = load_baseline(s.baseline_dir, pdf.stem)
        if base is None:
            t.add_row(pdf.stem, "-", "-", "-", "no baseline", "")
            continue
        diffs = diff_page(base, extract_pdf(pdf).pages[0])
        changed = [d for d in diffs if not d.identical]
        if not changed:
            t.add_row(pdf.stem, "[green]all sections identical[/green]", "", "", "", "")
        for d in changed:
            t.add_row(
                pdf.stem,
                d.section,
                str(d.n_baseline),
                str(d.n_new),
                "\n".join(d.only_baseline[:8]),
                "\n".join(d.only_new[:8]),
            )
    console.print(t)


@eval_app.command("seed")
def eval_seed(
    only: Annotated[
        list[str] | None, typer.Option("--only", help="build only this case (repeatable)")
    ] = None,
) -> None:
    """Rebuild the planted-error drawings (A5a) in data/eval/seeded from the samples in data/raw."""
    from drawing_intelligence.eval.seed import UnknownCaseError, seed_all

    s = get_settings()
    try:
        results = seed_all(s.raw_dir, s.data_path / "eval" / "seeded", only)
    except UnknownCaseError as e:
        raise typer.BadParameter(str(e), param_hint="--only") from e
    # what each case changed is in its case.json and the folder's README (its symbols trip some consoles)
    t = Table(title=f"Planted-error drawings ({len(results)} built)")
    for col in ("case", "kind", "edits"):
        t.add_column(col)
    for r in results:
        t.add_row(r.case, r.kind, str(len(r.edits)))
    console.print(t)


def _score_table(scores, targets) -> None:
    def cell(text: str, ok: bool | None) -> str:
        return text if ok is None else (f"[green]{text}[/green]" if ok else f"[red]{text}[/red]")

    t = Table(title="Understanding scorecard (green = target met)")
    for col in (
        "source",
        "drawing",
        "1 valid",
        "2 title block",
        "3 dims",
        "4 invented",
        "symbols",
        "time",
        "cost",
    ):
        t.add_column(col)
    for sc in scores:
        ok = sc.passed(targets)
        t.add_row(
            sc.source,
            sc.drawing,
            cell("yes" if sc.valid else "no", ok["1 valid"]),
            cell("no labels" if sc.title_block is None else f"{sc.title_block:.0%}", ok["2 title block"]),
            cell(f"{sc.dims_found}/{sc.dims_total}", ok["3 dims complete"]),
            cell(str(len(sc.invented)), ok["4 invented"]),
            str(sc.symbols),
            cell(f"{sc.seconds:.0f} s", ok["7 time"]),
            cell(_money(sc.cost_usd), ok["7 cost"]),
        )
    console.print(t)
    flags = [(sc.source, sc.drawing, w, n) for sc in scores for w, n in sc.invented]
    if flags:
        console.print(
            "[b]Numbers not found in the PDF text[/b] (a human decides: invention or harmless count?)"
        )
        for f in flags:
            console.print("  " + " · ".join(f))
    misses = [(sc.source, sc.drawing, *m) for sc in scores for m in sc.title_block_misses]
    if misses:
        console.print("[b]Title-block fields that differ from labels/title_block_truth.json[/b]")
        for src, d, f, want, got in misses:
            console.print(f"  {src} · {d} · {f}: expected {want!r}, got {got!r}")


@eval_app.command("understand")
def eval_understand(
    model: ModelOpt = None,
    thinking: ThinkingOpt = None,
    folder: Annotated[Path | None, typer.Option(help="PDF folder (default data/raw)")] = None,
    from_baseline: Annotated[
        bool, typer.Option("--from-baseline", help="score the notebook's saved outputs instead (free)")
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="skip the cost confirmation")] = False,
    runs: Annotated[int, typer.Option("--runs", help="repeat each drawing/model/thinking combo N times")] = 1,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="force a fresh call every run (uses a session-scoped cache)"),
    ] = False,
    max_seconds: float = 60.0,
    max_cost: float = 0.10,
) -> None:
    """Score understanding against criteria 1-4 and 7 of notebook 02."""
    from drawing_intelligence.eval.scorecard import Score, Targets, load_labels, score
    from drawing_intelligence.eval.stability import score_stability
    from drawing_intelligence.extraction import extract_pdf
    from drawing_intelligence.graph import run_workflow
    from drawing_intelligence.llm import load_registry

    s = get_settings()
    labels = load_labels(s.labels_dir)
    targets = Targets(max_seconds=max_seconds, max_cost_usd=max_cost)
    pdfs = _pdfs(folder)
    scores: list[Score] = []
    stability_runs: dict[str, list[dict]] = {}

    if from_baseline:
        for prov_dir in sorted((s.baseline_dir / "understanding").iterdir()):
            for pdf in pdfs:
                d = prov_dir / pdf.stem
                if not (d / "drawing_knowledge.json").exists():
                    continue
                raw = (
                    json.loads((d / "raw_run1.json").read_text(encoding="utf-8"))
                    if (d / "raw_run1.json").exists()
                    else {}
                )
                k = json.loads((d / "drawing_knowledge.json").read_text(encoding="utf-8"))
                scores.append(
                    score(
                        pdf.stem,
                        f"notebook:{raw.get('model', prov_dir.name)}",
                        k,
                        extract_pdf(pdf).pages[0],
                        seconds=raw.get("seconds", 0.0),
                        cost_usd=raw.get("cost_usd", 0.0),
                        truth=labels.get(pdf.stem),
                    )
                )
    else:
        spec = load_registry(s.config_path / "models.yaml").model(model, "understand")
        est = spec.cost(30_000, 10_000) * len(pdfs) * runs
        console.print(
            f"{len(pdfs)} drawing(s) x {runs} run(s) with {spec.name} "
            f"(thinking {spec.thinking_level(thinking)}): rough estimate {_money(est)} "
            f"if nothing is cached (30k in + 10k out tokens per page)."
        )
        if s.retention == "ephemeral":
            console.print("[yellow]DI_RETENTION=ephemeral: nothing is cached, every run pays again.[/yellow]")
        if not yes:
            typer.confirm("Make these API calls?", abort=True)
        run_settings = s
        if no_cache:
            try:
                run_settings = s.model_copy(update={"retention": "ephemeral"})
            except AttributeError:
                run_settings = s.copy(update={"retention": "ephemeral"})
        for pdf in pdfs:
            for run_idx in range(runs):
                res = run_workflow(pdf, run_settings, model=model, thinking=thinking)
                for page, r in zip(res.extraction.pages, res.understanding, strict=True):
                    key = pdf.stem if res.extraction.n_pages == 1 else f"{pdf.stem} p{page.page_number}"
                    label = f"{r.model}/{r.thinking}" + (f" run{run_idx + 1}" if runs > 1 else "")
                    scores.append(
                        score(
                            key,
                            label,
                            r.knowledge.model_dump(mode="json") if r.knowledge else None,
                            page,
                            seconds=r.latency_s,
                            cost_usd=r.cost_usd,
                            truth=labels.get(pdf.stem) if page.page_number == 1 else None,
                        )
                    )
                    if runs > 1 and r.knowledge:
                        stability_runs.setdefault(key, []).append(r.knowledge.model_dump(mode="json"))
    if labels and not json.loads((s.labels_dir / "title_block_truth.json").read_text(encoding="utf-8")).get(
        "_verified", True
    ):
        console.print(
            "[yellow]title_block_truth.json is a draft (_verified: false): "
            "criterion 2 is provisional.[/yellow]"
        )
    _score_table(scores, targets)
    console.print("Time and cost are those of the original call, also for cached replies.")
    if runs > 1 and stability_runs:
        console.print("\n[b]Stability across repeated runs (criterion 6)[/b]")
        st = Table("drawing", "runs", "title block stable?", "dim count stable?", "variants")
        for key, parsed in stability_runs.items():
            res = score_stability(parsed)
            st.add_row(
                key,
                str(res["n_runs"]),
                "[green]yes[/green]" if res["title_block_stable"] else "[red]no[/red]",
                "[green]yes[/green]" if res["dimension_count_stable"] else "[red]no[/red]",
                str(res["title_block_variants"]),
            )
        console.print(st)


def _pct(part: int, whole: int) -> str:
    return f"{part}/{whole} ({part / whole:.0%})" if whole else "-"


@eval_app.command("review")
def eval_review(
    model: ModelOpt = None,
    thinking: ThinkingOpt = None,
    no_understand: NoUnderstandOpt = False,
    no_llm_review: NoLlmReviewOpt = False,
    review_model: ReviewModelOpt = None,
    review_thinking: ReviewThinkingOpt = None,
    only: Annotated[
        list[str] | None, typer.Option("--only", help="case id prefix, e.g. P03 (repeatable)")
    ] = None,
    out: Annotated[Path | None, typer.Option("--out", help="also write the scores as JSON here")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="skip the cost confirmation")] = False,
) -> None:
    """Score the review on the planted-error drawings: recall, precision and false alarms (A5b)."""
    from drawing_intelligence.eval.answer_key import load_answer_keys
    from drawing_intelligence.eval.review_eval import run_review_eval, summarize
    from drawing_intelligence.llm import load_registry

    s = get_settings()
    root = s.data_path / "eval" / "seeded"
    n = len([k for k in load_answer_keys(root) if not only or any(k.case.startswith(o) for o in only)])
    if not no_understand:
        registry = load_registry(s.config_path / "models.yaml")
        spec = registry.model(model, "understand")
        est = spec.cost(30_000, 10_000) * n
        line = f"{n} case(s): understanding with {spec.name} (thinking {spec.thinking_level(thinking)})"
        if not no_llm_review:
            rspec = registry.model(review_model, "review")
            est += rspec.cost(10_000, 1_500) * 3 * n
            line += f", 3 LLM reviewers with {rspec.name} (thinking {rspec.thinking_level(review_thinking)})"
        console.print(f"{line}: rough estimate {_money(est)} if nothing is cached; cached replies are free.")
        if not yes:
            typer.confirm("Make these API calls?", abort=True)
    scores = run_review_eval(
        s,
        root,
        understand=not no_understand,
        llm_review=not no_llm_review,
        only=only,
        model=model,
        thinking=thinking,
        review_model=review_model,
        review_thinking=review_thinking,
    )

    t = Table(title="Review on the planted-error drawings")
    for col in ("case", "kind", "planted error caught", "findings", "false alarms"):
        t.add_column(col, overflow="fold")
    for c in scores:
        if c.kind == "planted":
            hit = "[green]yes[/green]" if all(c.caught) else ("no" if not any(c.covered) else "[red]no[/red]")
            hit += "" if any(c.covered) else " [dim](no check yet)[/dim]"
        else:
            hit = "-"
        fa = ", ".join(sorted({f.rule_id or "?" for f in c.false_alarms}))
        t.add_row(c.case, c.kind, hit, str(len(c.labels)), f"[red]{fa}[/red]" if fa else "0")
    console.print(t)

    sm = summarize(scores)
    console.print(f"Recall, all planted errors: {_pct(sm.caught, sm.planted)}")
    console.print(f"Recall, where a check is built: {_pct(sm.caught_covered, sm.covered)}")
    console.print(
        f"Precision: {_pct(sm.correct, sm.findings)} (findings: "
        + ", ".join(f"{k} {v}" for k, v in sorted(sm.labels.items()))
        + ")"
    )
    quiet = sm.false_alarms_on_quiet
    style = "red" if quiet else "green"
    console.print(
        f"[{style}]False alarms on clean and near-miss drawings (code checks): {len(quiet)}[/{style}]"
    )
    for case, f in quiet:
        console.print(f"  {case}: {f.rule_id} - {f.comment}")
    llm_quiet = sm.llm_alarms_on_quiet
    if any(f.source == "llm" for c in scores for f, _ in c.labels):
        console.print(
            f"LLM warnings on clean and near-miss drawings (measured, not a gate): {len(llm_quiet)}"
        )
        for case, f in llm_quiet:
            console.print(f"  {case}: {f.rule_id} ({f.reviewer}) - {f.comment}")
    cat = Table("category", "caught / planted")
    for k, (hit, total) in sm.by_category.items():
        cat.add_row(k, _pct(hit, total))
    rev = Table("reviewer", "correct / findings")
    for k, (ok, total) in sm.by_reviewer.items():
        rev.add_row(k, _pct(ok, total))
    console.print(cat, rev)
    cost = sum(c.cost_usd for c in scores)
    console.print(f"Billed this run: {_money(cost)} · review time {sum(c.latency_s for c in scores):.1f} s")
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "understand": not no_understand,
                    "recall": sm.recall,
                    "recall_covered": sm.recall_covered,
                    "precision": sm.precision,
                    "false_alarms_on_quiet": len(quiet),
                    "llm_alarms_on_quiet": len(llm_quiet),
                    "labels": dict(sm.labels),
                    "by_category": sm.by_category,
                    "by_reviewer": sm.by_reviewer,
                    "cases": [
                        {
                            "case": c.case,
                            "kind": c.kind,
                            "caught": c.caught,
                            "covered": c.covered,
                            "findings": [
                                {
                                    "rule_id": f.rule_id,
                                    "reviewer": f.reviewer,
                                    "label": lab,
                                    "comment": f.comment,
                                }
                                for f, lab in c.labels
                            ],
                        }
                        for c in scores
                    ],
                },
                indent=1,
            ),
            encoding="utf-8",
        )
        console.print(f"Scores written to {out}")


@eval_app.command("qa")
def eval_qa(
    model: ModelOpt = None,
    only: Annotated[
        list[str] | None, typer.Option("--only", help="case id prefix, e.g. h115 (repeatable)")
    ] = None,
    out: Annotated[
        Path | None, typer.Option("--out", help="also write every answer and score as JSON")
    ] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="skip the cost confirmation")] = False,
) -> None:
    """The Q&A agent on data/eval/qa/questions.yaml, scored by code (ADR 0011)."""
    from drawing_intelligence.eval.qa_eval import estimate_usd, load_questions, run_qa_eval

    s = get_settings()
    cases = [c for c in load_questions()["cases"] if not only or any(c["id"].startswith(o) for o in only)]
    n = sum(len(c["turns"]) for c in cases)
    est = estimate_usd(s, model, n)
    console.print(f"{len(cases)} conversations, {n} questions; at most ~{_money(est)} if nothing is cached.")
    if not yes and not typer.confirm("Run?"):
        raise typer.Exit()

    def show(t) -> None:
        mark = "[green]pass[/]" if t.passed else "[red]FAIL[/]"
        extra = "" if t.passed else f"  [dim]{'; '.join(t.missing)}[/]"
        console.print(f"{mark} {t.case}#{t.turn} ({t.kind}) {_money(t.cost_usd)}{extra}")

    res = run_qa_eval(s, model, only, on_turn=show)
    summary = res.summary()
    table = Table("measure", "value")
    for k, v in summary.items():
        table.add_row(k, str(v))
    console.print(table)
    console.print(
        "Bar (ADR 0011): verified >= 90%, no answer with unverified numbers, every decline and guard passed: "
        + ("[green]met[/]" if summary["meets_bar"] else "[red]not met[/]")
    )
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        rows = [t.__dict__ for t in res.turns]
        out.write_text(
            json.dumps({"summary": summary, "answers": rows}, ensure_ascii=False, indent=1), "utf-8"
        )
        console.print(f"Answers written to {out}")


@eval_app.command("heldout")
def eval_heldout(
    out: Annotated[Path, typer.Option("--out", help="where the reports and findings.csv go")],
    n: Annotated[int, typer.Option("--n", help="how many unseen client drawings")] = 25,
    seed: Annotated[int, typer.Option("--seed", help="random seed of the selection")] = 2026,
    drawings_file: Annotated[
        Path | None,
        typer.Option("--drawings", help="re-run a listed set (paths relative to data/client_set)"),
    ] = None,
    no_understand: NoUnderstandOpt = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="skip the cost confirmation")] = False,
) -> None:
    """Review unseen client drawings and write findings.csv for an engineer to label (held-out validation)."""
    from drawing_intelligence.eval.heldout import run_heldout, select_heldout
    from drawing_intelligence.llm import load_registry

    s = get_settings()
    client = s.data_path / "client_set"
    if drawings_file is not None:
        names = [ln.strip() for ln in drawings_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
        drawings = [client / name for name in names]
    else:
        drawings = select_heldout(client, n, seed, samples_dir=s.raw_dir)
    if not no_understand:
        registry = load_registry(s.config_path / "models.yaml")
        est = registry.model(None, "understand").cost(30_000, 10_000) + 3 * registry.model(
            None, "review"
        ).cost(10_000, 1_500)
        console.print(
            f"{len(drawings)} drawing(s), full review: rough estimate {_money(est * len(drawings))}."
        )
        if not yes:
            typer.confirm("Make these API calls?", abort=True)
    runs = run_heldout(s, drawings, out, understand=not no_understand)
    t = Table("drawing", "findings", "variant title block", "cost", "error")
    for r in runs:
        t.add_row(
            r.drawing,
            str(r.findings),
            "yes" if r.variant_title_block else "",
            _money(r.cost_usd),
            r.error or "",
        )
    console.print(t)
    console.print(
        f"{sum(r.findings for r in runs)} findings on {len(runs)} drawings; "
        f"billed {_money(sum(r.cost_usd for r in runs))}. Label them in {out / 'findings.csv'}."
    )
