from inspect import Parameter, Signature
from typing import Annotated, Any, Optional

import typer

from umbod.config import AppConfig, load_server_app_config
from umbod.logging import configure_logging

app = typer.Typer(help="REST API server commands.", no_args_is_help=True)


def run_api_server(settings: AppConfig, host: str, port: int, reload: bool) -> None:
    from umbod.hosting.api_server import run_api_server as delegate

    delegate(settings, host, port, reload)


def validate_listener_ports(settings: AppConfig, port: int) -> None:
    from umbod.hosting.api_server import validate_listener_ports as delegate

    delegate(settings, port)


class ServeCommand:
    __name__ = "serve"
    __signature__ = Signature(
        parameters=[
            Parameter(
                "host",
                Parameter.POSITIONAL_OR_KEYWORD,
                default="0.0.0.0",
                annotation=Annotated[
                    str,
                    typer.Option(help="Host interface to bind."),
                ],
            ),
            Parameter(
                "port",
                Parameter.POSITIONAL_OR_KEYWORD,
                default=None,
                annotation=Annotated[Optional[int], typer.Option(help="Port to bind.")],
            ),
            Parameter(
                "reload",
                Parameter.POSITIONAL_OR_KEYWORD,
                default=False,
                annotation=Annotated[
                    bool,
                    typer.Option(help="Reload when source files change."),
                ],
            ),
        ],
        return_annotation=None,
    )

    def __call__(self, **kwargs: Any) -> None:
        try:
            settings = load_server_app_config(".env")
        except ValueError as error:
            typer.echo(str(error), err=True)
            raise typer.Exit(code=1) from None
        configured_port = (
            settings.rest.port if kwargs["port"] is None else int(kwargs["port"])
        )
        try:
            validate_listener_ports(settings, configured_port)
        except ValueError as error:
            typer.echo(str(error), err=True)
            raise typer.Exit(code=1) from None
        configure_logging(settings.runtime.app_name, settings.runtime.log_level)
        try:
            run_api_server(
                settings,
                host=str(kwargs["host"]),
                port=configured_port,
                reload=bool(kwargs["reload"]),
            )
        except (OSError, RuntimeError) as _error:
            typer.echo("Unable to run Umbod HTTP listeners.", err=True)
            raise typer.Exit(code=1) from None


app.command("serve")(ServeCommand())
