"""Command-line entry point.

Exit codes (``profile``):
  0  a profile was produced, whatever its status (NOT_FOUND and AMBIGUOUS are valid answers)
  1  system failure (missing or malformed data files)
  2  invalid input (empty / legal-form-only name, bad --as-of)
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import date
from typing import Annotated

import typer

from uw_agent.agent import ProfilePipeline
from uw_agent.config import Settings
from uw_agent.data import DataRepository, DataSchemaError
from uw_agent.data.quality import run_quality_checks
from uw_agent.resolution import EntityResolver
from uw_agent.schema.profile import ProfileStatus

app = typer.Typer(add_completion=False, help="Underwriting intelligence agent")

EXIT_OK, EXIT_SYSTEM, EXIT_INPUT = 0, 1, 2


def _repo(settings: Settings) -> DataRepository:
    try:
        return DataRepository.load(settings.data_dir)
    except DataSchemaError as exc:
        typer.echo(f"Error de datos: {exc}", err=True)
        raise typer.Exit(EXIT_SYSTEM) from exc


def _as_of(value: str | None, settings: Settings) -> date:
    if not value:
        return settings.as_of_date
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        typer.echo(f"--as-of inválido '{value}': use AAAA-MM-DD", err=True)
        raise typer.Exit(EXIT_INPUT) from exc


@app.command()
def profile(
    name: Annotated[str, typer.Argument(help="Company name as typed by the underwriter")],
    state: Annotated[
        str | None, typer.Option(help="Optional state to disambiguate homonyms")
    ] = None,
    as_of: Annotated[str | None, typer.Option("--as-of", help="Reference date YYYY-MM-DD")] = None,
) -> None:
    """Build the underwriting profile for one company and print it as JSON."""
    settings = Settings.from_env()
    reference = _as_of(as_of, settings)
    pipeline = ProfilePipeline(_repo(settings))
    result = pipeline.build(name, as_of=reference, state=state)
    typer.echo(result.model_dump_json(indent=2))
    if result.status is ProfileStatus.INVALID_INPUT:
        raise typer.Exit(EXIT_INPUT)


@app.command()
def resolve(
    name: Annotated[str, typer.Argument(help="Company name as typed by the underwriter")],
    state: Annotated[str | None, typer.Option(help="Optional state to disambiguate")] = None,
) -> None:
    """Resolve a company name to a portfolio ClientId (entity resolution only)."""
    resolver = EntityResolver.from_repository(_repo(Settings.from_env()))
    typer.echo(resolver.resolve(name, state=state).model_dump_json(indent=2))


@app.command("data-quality")
def data_quality() -> None:
    """Run dataset-level data-quality checks and print them as JSON."""
    settings = Settings.from_env()
    issues = run_quality_checks(_repo(settings), settings.as_of_date)
    typer.echo(json.dumps([asdict(i) for i in issues], indent=2, ensure_ascii=False))


@app.command("schema")
def schema() -> None:
    """Print the JSON Schema of the underwriting profile."""
    from uw_agent.schema import UnderwritingProfile

    typer.echo(json.dumps(UnderwritingProfile.model_json_schema(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    app(prog_name="uw-agent")
    sys.exit(EXIT_OK)
