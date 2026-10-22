from inspect import Parameter, Signature
from typing import Annotated, Any, Optional

import typer
import uvicorn

from umbod.config import load_server_app_config
from umbod.logging import configure_logging

app = typer.Typer(help="MCP server commands.", no_args_is_help=True)


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
        configure_logging(settings.runtime.app_name, settings.runtime.log_level)
        configured_port = settings.mcp.port if kwargs["port"] is None else int(kwargs["port"])
        uvicorn.run(
            "umbod.hosting.mcp_service:app",
            host=str(kwargs["host"]),
            port=configured_port,
            reload=bool(kwargs["reload"]),
            log_level=settings.runtime.log_level,
            log_config=None,
        )


app.command("serve")(ServeCommand())
