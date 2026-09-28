from pathlib import Path
from typing import Annotated

import typer

from umbod_sdk.connector_init import InitError, InitRequest, create_initializer


def init(
    name: Annotated[str, typer.Option(help="Lowercase hyphen-separated connector ID.")],
    module: Annotated[str, typer.Option(help="Existing package and new module, e.g. my_package.hello_world.")],
    project: Annotated[Path, typer.Option(help="Project directory (defaults to current directory). ")] = Path("."),
    apply: Annotated[bool, typer.Option("--apply", help="Write the previewed changes.")] = False,
) -> None:
    initializer = create_initializer()
    try:
        plan = initializer.plan(InitRequest(project_directory=str(project), name=name, module=module))
    except (InitError, OSError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"Planned source for {plan.module_path}:\n{plan.source}")
    typer.echo(f"Planned addition to {plan.metadata_path}:\n{plan.metadata_addition.decode('utf-8')}")
    if apply:
        try:
            initializer.apply(plan)
        except (InitError, OSError) as error:
            typer.echo(str(error), err=True)
            raise typer.Exit(code=1) from error
        typer.echo(f"Applied connector initialization to {plan.module_path} and {plan.metadata_path}.")
    else:
        typer.echo("Preview only; use --apply to write.")
    typer.echo("Manage dependencies with uv yourself, then run umbod connectors check for static metadata checks.")
