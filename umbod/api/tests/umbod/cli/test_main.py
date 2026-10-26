from typer.main import get_command
from typer.testing import CliRunner

from umbod.cli.main import app


def test_supported_command_groups_exclude_retired_filesystem_command() -> None:
    command = get_command(app)

    assert set(command.commands) == {"api", "config", "connectors", "mcp"}


def test_retired_filesystem_command_is_rejected() -> None:
    result = CliRunner().invoke(app, ["filesystem", "bootstrap"])

    assert result.exit_code == 2
    assert "No such command" in result.output
