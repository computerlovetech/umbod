from inspect import Parameter, Signature
from typing import Annotated, Any, Optional

import typer
import uvicorn

from umbod.config import load_app_config
from umbod.logging import configure_logging

app = typer.Typer(help="REST API server commands.", no_args_is_help=True)


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
        settings = load_app_config(".env")
        configure_logging(settings.runtime.app_name, settings.runtime.log_level)
        configured_port = settings.rest.port if kwargs["port"] is None else int(kwargs["port"])
        uvicorn.run(
            "umbod.rest.main:create_app",
            host=str(kwargs["host"]),
            port=configured_port,
            reload=bool(kwargs["reload"]),
            log_level=settings.runtime.log_level,
            log_config=None,
            factory=True,
        )


app.command("serve")(ServeCommand())
