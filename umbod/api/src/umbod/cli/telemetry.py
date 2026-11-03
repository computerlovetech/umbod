from inspect import Parameter, Signature
from typing import Annotated, Any, Optional

import typer
import uvicorn

from umbod.config.telemetry import load_telemetry_app_config
from umbod.logging import configure_logging

app = typer.Typer(help="Telemetry receiver commands.", no_args_is_help=True)


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
