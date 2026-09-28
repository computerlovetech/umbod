from pathlib import Path
from typing import Annotated

import typer

from umbod_sdk.connector_checks import create_checker
from umbod_sdk.connector_checks.checker import MetadataCheckError
from umbod_sdk.connector_checks.models import MetadataRequest
from umbod_sdk.connector_checks.port import MetadataReadError

connectors_app = typer.Typer(help="Check connector project metadata.", no_args_is_help=True)


@connectors_app.command("check")
def check(
    project: Annotated[Path, typer.Option(help="Connector project directory (defaults to current directory).")] = Path("."),
) -> None:
    request = MetadataRequest(project_directory=str(project))
    try:
        result = create_checker().check(request)
    except (MetadataReadError, MetadataCheckError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        f"Valid connector entry-point metadata for {len(result.entry_names)} entry(s) in {project / 'pyproject.toml'}. "
        "Runtime loading and target-release compatibility were not checked."
    )
