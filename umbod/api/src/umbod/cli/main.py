import typer

from umbod.cli.api import app as api_app
from umbod.cli.config import app as config_app
from umbod.cli.connectors import app as connectors_app
from umbod.cli.mcp import app as mcp_app
from umbod.cli.migrate import app as migrate_app
from umbod.cli.telemetry import app as telemetry_app

app = typer.Typer(help="Umbod CLI.", no_args_is_help=True)
app.add_typer(api_app, name="api", help="REST API server commands.")
app.add_typer(config_app, name="config", help="Configuration inspection commands.")
app.add_typer(connectors_app, name="connectors", help="Connector plugin inspection commands.")
app.add_typer(mcp_app, name="mcp", help="MCP server commands.")
app.add_typer(telemetry_app, name="telemetry", help="Telemetry receiver commands.")
app.add_typer(migrate_app, name="migrate", help="Offline deployment data migrations.")


def run() -> None:
    app()
