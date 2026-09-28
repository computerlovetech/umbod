from pathlib import Path
from typing import Annotated

import typer

from umbod_sdk.connector_checks import (
    create_checker,
    create_compatibility_checker,
    create_release_reader,
)
from umbod_sdk.connector_checks.checker import MetadataCheckError
from umbod_sdk.connector_checks.compatibility import (
    ReleaseMetadataError,
    ReleaseRequest,
    SdkVersion,
)
from umbod_sdk.connector_checks.models import MetadataRequest
from umbod_sdk.connector_checks.port import MetadataReadError

connectors_app = typer.Typer(help="Check and initialize connector projects.", no_args_is_help=True)


@connectors_app.command("check")
def check(
    project: Annotated[Path, typer.Option(help="Connector project directory (defaults to current directory).")] = Path("."),
    target: Annotated[str | None, typer.Option(help="Published synchronized image release; reads core and builder registry metadata.")] = None,
    sdk_version: Annotated[str | None, typer.Option(help="Explicit SDK version for an offline declaration check; does not verify an image.")] = None,
) -> None:
    if target is not None and sdk_version is not None:
        raise typer.BadParameter("Use --target or --sdk-version, not both")
    request = MetadataRequest(project_directory=str(project))
    try:
        result = create_checker().check(request)
        if target is None and sdk_version is None:
            typer.echo(
                f"Valid connector entry-point metadata for {len(result.entry_names)} entry(s) in {project / 'pyproject.toml'}. "
                "Runtime loading and target-release compatibility were not checked."
            )
            return
        candidate = create_release_reader().read(ReleaseRequest(release=target)) if target is not None else SdkVersion(version=sdk_version)
        compatibility = create_compatibility_checker().check(request, candidate)
        if not compatibility.compatible:
            raise MetadataCheckError(
                f"{project / 'pyproject.toml'}: {compatibility.requirement} does not accept SDK {compatibility.sdk_version}. "
                "Choose a compatible SDK target or review the declared requirement; no files were changed."
            )
    except (MetadataReadError, MetadataCheckError, ReleaseMetadataError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    provenance = f"published target {target}" if target is not None else "explicit SDK version; image not verified"
    typer.echo(
        f"Entry-point metadata passed. Declared dependency {compatibility.requirement} accepts SDK "
        f"{compatibility.sdk_version} ({provenance}). Runtime loading and external-service compatibility were not checked."
    )
