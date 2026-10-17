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
eval_app = typer.Typer(help="Evaluate extraction and understanding.", no_args_is_help=True)
app.add_typer(eval_app, name="eval")
console = Console()

ModelOpt = Annotated[str | None, typer.Option("--model", "-m", help="registered model (see `di models`)")]
ThinkingOpt = Annotated[str | None, typer.Option("--thinking", "-t", help="thinking option of that model")]
ExportOpt = Annotated[
    Path | None, typer.Option("--export", help="keep a copy of the outputs and annotated images here")
]


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
    """Validate the rulebook and summarise it: rules per category, check type and status."""
    from collections import Counter

    from drawing_intelligence.review import RulebookError, load_rulebook
    from drawing_intelligence.schemas.review import CATEGORY_LABELS

    try:
        book = load_rulebook(folder)
    except RulebookError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e
    if not book.rules:
        console.print("The rulebook is empty: add rules in config/rules/*.yaml (see config/rules/README.md).")
        return
    t = Table(title=f"Rulebook {book.version} ({len(book.rules)} rules)")
    for col in ("category", "rules", "code", "lookup", "llm", "client confirmed"):
        t.add_column(col)
    by_cat: dict[str, Counter] = {}
    for r in book.rules:
        c = by_cat.setdefault(r.category, Counter())
        c["rules"] += 1
        c[r.check_type] += 1
        c["confirmed"] += r.status == "client_confirmed"
    for cat, c in by_cat.items():
        t.add_row(
            CATEGORY_LABELS[cat],
            *(str(c[k]) for k in ("rules", "code", "lookup", "llm", "confirmed")),
        )
    console.print(t)


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
