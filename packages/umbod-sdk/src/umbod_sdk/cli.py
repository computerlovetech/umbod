from pathlib import Path
from typing import Annotated

import typer

from umbod_sdk.skill_installation import (
    Harness,
    Scope,
    bundled_skills,
    install_skills,
    skills_directory,
)

app = typer.Typer(help="Umbod SDK tools.", no_args_is_help=True)
skills_app = typer.Typer(help="Manage bundled agent skills.", no_args_is_help=True)
app.add_typer(skills_app, name="skills")


@skills_app.command("list")
def list_skills() -> None:
    for name in bundled_skills():
        typer.echo(name)


@skills_app.command("install")
def install(
    skill_name: Annotated[str | None, typer.Argument(help="Bundled skill to install.")] = None,
    harness: Annotated[Harness | None, typer.Option(help="Target agent harness.")] = None,
    scope: Annotated[Scope, typer.Option(help="Project or user-wide installation.")] = Scope.project,
    project: Annotated[Path | None, typer.Option(help="Project directory (defaults to current directory).")] = None,
    all_skills: Annotated[bool, typer.Option("--all", help="Install every bundled skill.")] = False,
    force: Annotated[bool, typer.Option(help="Replace existing skill directories.")] = False,
) -> None:
    if harness is None:
        raise typer.BadParameter("--harness is required")
    if all_skills == (skill_name is not None):
        raise typer.BadParameter("Provide a skill name or --all, but not both")
    if project is not None and scope is Scope.user:
        raise typer.BadParameter("--project requires --scope project")

    names = bundled_skills() if all_skills else [skill_name] if skill_name is not None else []
    destination = skills_directory(harness, scope, project)
    try:
        installed = install_skills(names, destination, force=force)
    except (OSError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    for path in installed:
        typer.echo(path)
