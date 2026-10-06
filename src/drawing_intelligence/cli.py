"""The `di` command line."""

from __future__ import annotations

import typer

from drawing_intelligence import __version__

app = typer.Typer(
    help="Drawing Intelligence: agentic AI review of 2D engineering drawings.", no_args_is_help=True
)


@app.callback()
def main() -> None:
    """Drawing Intelligence: agentic AI review of 2D engineering drawings."""


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)
