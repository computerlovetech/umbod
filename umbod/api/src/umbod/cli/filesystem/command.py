import asyncio
from typing import Annotated

import typer
from pydantic import ValidationError

from umbod.config import load_app_config
from umbod.core.filesystem import ProvisioningConflict
from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider

from .policy import FileBootstrapPolicySource
from .ports import BootstrapPolicySource
from .service import bootstrap_root

app = typer.Typer(help="Trusted operator-only filesystem administration.", no_args_is_help=True)


@app.command("bootstrap")
def bootstrap(
    policy_file: Annotated[
        str,
        typer.Option("--policy-file", help="Required trusted JSON bootstrap policy file; /dev/stdin is supported."),
    ],
) -> None:
    source: BootstrapPolicySource = FileBootstrapPolicySource()
    try:
        spec = source.load(policy_file)
    except (OSError, ValueError, ValidationError):
        typer.echo("Bootstrap policy could not be read or is invalid. Supply a valid trusted JSON policy file.", err=True)
        raise typer.Exit(code=1) from None
    try:
        config = load_app_config(".env")
        provider = ConfiguredPersistenceRuntimeProvider(config.connector_store)
        asyncio.run(bootstrap_root(spec, provider))
    except ProvisioningConflict:
        typer.echo(
            "Filesystem root bootstrap conflict. An operator must inspect existing root ownership and data; "
            "use an explicit migration or recovery procedure before retrying. No automatic adoption is performed.",
            err=True,
        )
        raise typer.Exit(code=1) from None
    except (Exception, asyncio.CancelledError, KeyboardInterrupt):
        typer.echo("Filesystem root bootstrap failed. Check configuration and persistence availability before retrying.", err=True)
        raise typer.Exit(code=1) from None
    typer.echo("Filesystem root bootstrap completed. Bootstrap does not reconcile existing grants.")
