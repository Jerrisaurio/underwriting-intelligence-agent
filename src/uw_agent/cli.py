"""Command-line entry point.

Implemented so far: ``resolve`` (entity resolution only) and ``data-quality``.
``profile`` and ``batch`` arrive with the agent phase.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Annotated

import typer

from uw_agent.config import Settings
from uw_agent.data import DataRepository
from uw_agent.data.quality import run_quality_checks
from uw_agent.resolution import EntityResolver

app = typer.Typer(add_completion=False, help="Underwriting intelligence agent")


def _repo(settings: Settings) -> DataRepository:
    return DataRepository.load(settings.data_dir)


@app.command()
def resolve(
    name: Annotated[str, typer.Argument(help="Company name as typed by the underwriter")],
    state: Annotated[str | None, typer.Option(help="Optional state to disambiguate")] = None,
) -> None:
    """Resolve a company name to a portfolio ClientId and print the result as JSON."""
    resolver = EntityResolver.from_repository(_repo(Settings.from_env()))
    typer.echo(resolver.resolve(name, state=state).model_dump_json(indent=2))


@app.command("data-quality")
def data_quality() -> None:
    """Run dataset-level data-quality checks and print them as JSON."""
    settings = Settings.from_env()
    issues = run_quality_checks(_repo(settings), settings.as_of_date)
    typer.echo(json.dumps([asdict(i) for i in issues], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    app()
