import asyncio
from datetime import datetime
from inspect import Parameter, Signature
from typing import Annotated, Any, Optional

import typer
import uvicorn

from umbod.config import load_server_app_config
from umbod.config.telemetry import load_telemetry_app_config
from umbod.core.telemetry.analytics.backfill import (
    BackfillSelectionLimitExceeded,
    BackfillWindow,
    ReplayBatch,
)
from umbod.infrastructure import create_log_archive_backfill
from umbod.logging import configure_logging

app = typer.Typer(help="Telemetry receiver commands.", no_args_is_help=True)

_DEFAULT_BACKFILL_LIMIT = 100


class ServeCommand:
    __name__ = "serve"
    __signature__ = Signature(
        parameters=[
            Parameter(
                "host",
                Parameter.POSITIONAL_OR_KEYWORD,
                default=None,
                annotation=Annotated[
                    Optional[str], typer.Option(help="Host interface to bind.")
                ],
            ),
            Parameter(
                "port",
                Parameter.POSITIONAL_OR_KEYWORD,
                default=None,
                annotation=Annotated[
                    Optional[int],
                    typer.Option(min=1, max=65535, help="Port to bind."),
                ],
            ),
            Parameter(
                "reload",
                Parameter.POSITIONAL_OR_KEYWORD,
                default=False,
                annotation=Annotated[
                    bool, typer.Option(help="Reload when source files change.")
                ],
            ),
        ],
        return_annotation=None,
    )

    def __call__(self, **kwargs: Any) -> None:
        try:
            settings = load_telemetry_app_config(".env")
        except ValueError:
            typer.echo("Invalid telemetry configuration.", err=True)
            raise typer.Exit(code=1) from None
        configured_host = (
            settings.otlp_receiver.host
            if kwargs["host"] is None
            else str(kwargs["host"])
        )
        configured_port = (
            settings.otlp_receiver.port
            if kwargs["port"] is None
            else int(kwargs["port"])
        )
        configure_logging(settings.runtime.app_name, settings.runtime.log_level)
        uvicorn.run(
            "umbod.hosting.telemetry_service:create_app",
            host=configured_host,
            port=configured_port,
            reload=bool(kwargs["reload"]),
            log_level=settings.runtime.log_level,
            log_config=None,
            factory=True,
        )


app.command("serve")(ServeCommand())


class BackfillCommand:
    __name__ = "backfill"
    __signature__ = Signature(
        parameters=[
            Parameter(
                "batch_id",
                Parameter.POSITIONAL_OR_KEYWORD,
                default=None,
                annotation=Annotated[Optional[str], typer.Option(help="Archive batch ID.")],
            ),
            Parameter(
                "start",
                Parameter.POSITIONAL_OR_KEYWORD,
                default=None,
                annotation=Annotated[
                    Optional[str], typer.Option("--from", help="Inclusive receipt time (offset-aware ISO 8601).")
                ],
            ),
            Parameter(
                "end",
                Parameter.POSITIONAL_OR_KEYWORD,
                default=None,
                annotation=Annotated[
                    Optional[str], typer.Option("--to", help="Exclusive receipt time (offset-aware ISO 8601).")
                ],
            ),
            Parameter(
                "limit",
                Parameter.POSITIONAL_OR_KEYWORD,
                default=None,
                annotation=Annotated[
                    Optional[str],
                    typer.Option(help=f"Maximum matched batches for a date range (default: {_DEFAULT_BACKFILL_LIMIT})."),
                ],
            ),
            Parameter(
                "apply",
                Parameter.POSITIONAL_OR_KEYWORD,
                default=False,
                annotation=Annotated[bool, typer.Option("--apply", help="Replace unified rows instead of previewing.")],
            ),
        ],
        return_annotation=None,
    )

    def __call__(self, apply: bool, **options: object) -> None:
        selection = _parse_backfill_selection({name: value for name, value in options.items() if isinstance(value, str)})
        try:
            asyncio.run(_run_backfill(selection, apply=apply))
        except BackfillSelectionLimitExceeded:
            typer.echo("Selection exceeds the batch limit. Narrow the date range or increase --limit.", err=True)
            raise typer.Exit(code=1) from None
        except typer.Exit:
            raise
        except Exception:
            typer.echo("Backfill stopped. Check the server configuration and archive availability.", err=True)
            raise typer.Exit(code=1) from None


app.command("backfill")(BackfillCommand())


def _parse_backfill_selection(options: dict[str, str]) -> ReplayBatch | BackfillWindow:
    if options.keys() == {"batch_id"}:
        try:
            return ReplayBatch(batch_id=int(options["batch_id"]))
        except ValueError:
            raise typer.BadParameter("Expected a positive archive batch ID.", param_hint="--batch-id") from None
    if {"start", "end"} <= options.keys() <= {"start", "end", "limit"}:
        try:
            return BackfillWindow(
                start=datetime.fromisoformat(options["start"]),
                end=datetime.fromisoformat(options["end"]),
                limit=int(options.get("limit", str(_DEFAULT_BACKFILL_LIMIT))),
            )
        except (ValueError, OverflowError):
            raise typer.BadParameter(
                "Expected offset-aware ISO 8601 times with --from before --to and a positive batch limit.",
                param_hint="--from / --to / --limit",
            ) from None
    raise typer.BadParameter("Choose --batch-id alone or both --from and --to. --limit is only for date ranges.")


async def _run_backfill(selection: ReplayBatch | BackfillWindow, *, apply: bool) -> None:
    config = load_server_app_config(".env")
    async with create_log_archive_backfill(config, apply=apply) as store:
        batches = (selection,) if isinstance(selection, ReplayBatch) else await store.select(selection)
        mode = "Apply" if apply else "Preview"
        operation = store.apply if apply else store.preview
        total = len(batches)
        typer.echo(f"{mode}: selected {total} batch(es).")
        for index, batch in enumerate(batches, start=1):
            typer.echo(f"{mode} {index}/{total}: batch_id={batch.batch_id}", err=True)
            try:
                summary = await operation(batch)
            except Exception:
                typer.echo(
                    f"{mode} stopped at batch_id={batch.batch_id}: {index - 1} of {total} batch(es) completed.",
                    err=True,
                )
                raise typer.Exit(code=1) from None
            typer.echo(
                f"batch_id={summary.batch_id} received_at={summary.received_at.isoformat()} "
                f"record_count={summary.record_count}"
            )
    typer.echo(f"{mode} complete: {total} batch(es).")
