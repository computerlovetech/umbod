import json
from inspect import Parameter, Signature
from typing import Annotated, Any

import typer

from umbod.config import load_app_config, safe_app_config_dump

app = typer.Typer(help="Configuration inspection commands.", no_args_is_help=True)


class ValidateCommand:
    __name__ = "validate"
    __signature__ = Signature(parameters=[], return_annotation=None)

    def __call__(self) -> None:
        try:
            load_app_config(".env")
        except ValueError as error:
            typer.echo(f"Configuration invalid: {error}", err=True)
            raise typer.Exit(code=1) from error
        typer.echo("Configuration valid.")


class ShowCommand:
    __name__ = "show"
    __signature__ = Signature(
        parameters=[
            Parameter(
                "advanced",
                Parameter.POSITIONAL_OR_KEYWORD,
                default=False,
                annotation=Annotated[
                    bool,
                    typer.Option(help="Include advanced runtime and connector settings."),
                ],
            ),
        ],
        return_annotation=None,
    )

    def __call__(self, **kwargs: Any) -> None:
        try:
            config = load_app_config(".env")
        except ValueError as error:
            typer.echo(f"Configuration invalid: {error}", err=True)
            raise typer.Exit(code=1) from error
        data = safe_app_config_dump(config)
        if not bool(kwargs["advanced"]):
            data = _summary_view(data)
        typer.echo(json.dumps(data, indent=2, sort_keys=True))


def _summary_view(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "runtime": data["runtime"],
        "endpoints": data["endpoints"],
        "connector_store": {"type": data["connector_store"]["type"]},
        "admin_authentication": {
            "environment": data["admin_authentication"]["environment"],
            "mode": data["admin_authentication"]["mode"],
            "required_membership": data["admin_authentication"]["required_membership"],
        },
        "mcp": {
            "auth_mode": data["mcp"]["auth_mode"],
            "connector_tool_exposure_mode": data["mcp"]["connector_tool_exposure_mode"],
        },
        "oidc": {"provider": data["oidc"]["provider"]},
    }


app.command("validate")(ValidateCommand())
app.command("show")(ShowCommand())
