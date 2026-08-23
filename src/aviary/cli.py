"""Command line interface."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from typing import Annotated

import typer

from aviary.ingestion.fed import fetch_statements
from aviary.logging import get_logger, run_context

app = typer.Typer(help="Analyse central bank communication.", no_args_is_help=True)
log = get_logger(__name__)

DEFAULT_CACHE_DIR = Path("data/raw")


@app.callback()
def main() -> None:
    """Analyse central bank communication."""


@app.command()
def fetch(
    since: Annotated[
        str | None,
        typer.Option(help="Only fetch statements released on or after this date (YYYY-MM-DD)."),
    ] = None,
    cache_dir: Annotated[
        Path,
        typer.Option(help="Where to store fetched HTML."),
    ] = DEFAULT_CACHE_DIR,
) -> None:
    """Download FOMC statements to the local cache."""
    cutoff = date.fromisoformat(since) if since else None

    with run_context():
        statements = asyncio.run(fetch_statements(cache_dir, since=cutoff))

    typer.echo(f"Retrieved {len(statements)} statements into {cache_dir}")


if __name__ == "__main__":
    app()
