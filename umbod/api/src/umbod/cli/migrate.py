import asyncio
from inspect import Parameter, Signature
from pathlib import Path
from typing import Annotated

import typer

from umbod.config import OperatorSettings, S3FilesystemContentConfig, build_app_config
from umbod.core.filesystem import StorageFailure
from umbod.infrastructure import S3ContentConfig, migrate_local_content

app = typer.Typer(help="Offline deployment data migrations.", no_args_is_help=True)


class FilesToS3Command:
    __name__ = "files_to_s3"
    __signature__ = Signature(
        parameters=[
            Parameter(
                "source",
                Parameter.POSITIONAL_OR_KEYWORD,
                default="",
                annotation=Annotated[
                    str,
                    typer.Option(help="Local source override; defaults to the configured local content directory."),
                ],
            ),
            Parameter(
                "dry_run",
                Parameter.POSITIONAL_OR_KEYWORD,
                default=False,
                annotation=Annotated[
                    bool,
                    typer.Option(help="Inspect and verify without writing S3 objects."),
                ],
            ),
            Parameter(
                "offline",
                Parameter.POSITIONAL_OR_KEYWORD,
                default=False,
                annotation=Annotated[
                    bool,
                    typer.Option(help="Confirm all API/MCP services and other file writers are stopped."),
                ],
            ),
        ],
        return_annotation=None,
    )

    def __call__(self, source: str, dry_run: bool, offline: bool) -> None:
        if not offline:
            typer.echo("Stop all file writers, then pass --offline to confirm.", err=True)
            raise typer.Exit(code=2)
        try:
            operator = OperatorSettings(_env_file=".env")
            content = build_app_config(operator).filesystem.content
            if not isinstance(content, S3FilesystemContentConfig):
                typer.echo("Migration requires a configured S3 content backend.", err=True)
                raise typer.Exit(code=2)
            target = S3ContentConfig.model_validate(content.model_dump())
            source_directory = Path(
                source or operator.filesystem_content_directory
                or str(Path(operator.data_dir).expanduser() / "filesystem-content")
            ).expanduser()
            result = asyncio.run(migrate_local_content(
                source=source_directory, target=target, dry_run=dry_run,
            ))
        except (ValueError, OSError, StorageFailure):
            typer.echo(
                "Migration failed. Check configuration, source directory, S3 access and content conflicts. "
                "Local files are retained; fix the cause and rerun before switching services.",
                err=True,
            )
            raise typer.Exit(code=1) from None
        prefix = "Dry run" if dry_run else "Migration complete"
        typer.echo(
            f"{prefix}: copied={result.copied}, identical={result.skipped}, "
            f"planned={result.planned}, bytes={result.total_bytes}. Local files retained."
        )


app.command("files-to-s3")(FilesToS3Command())
