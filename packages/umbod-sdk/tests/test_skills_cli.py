from pathlib import Path

import pytest
from typer.testing import CliRunner

from umbod_sdk.cli import app


@pytest.mark.parametrize(
    ("harness", "folder"),
    [("claude", ".claude"), ("codex", ".agents"), ("agents", ".agents")],
)
def test_install_skill_in_project(tmp_path: Path, harness: str, folder: str) -> None:
    result = CliRunner().invoke(
        app, ["skills", "install", "draft-agent-connector", "--harness", harness, "--project", str(tmp_path)]
    )

    target = tmp_path / folder / "skills" / "draft-agent-connector"
    assert result.exit_code == 0, result.output
    assert (target / "SKILL.md").is_file()
    assert (target / "REFERENCE.md").is_file()
    assert str(target) in result.output


def test_list_and_install_all(tmp_path: Path) -> None:
    runner = CliRunner()
    listed = runner.invoke(app, ["skills", "list"])
    installed = runner.invoke(app, ["skills", "install", "--all", "--harness", "codex", "--project", str(tmp_path)])

    assert listed.exit_code == 0
    assert "draft-agent-connector" in listed.output
    assert installed.exit_code == 0, installed.output
    assert (tmp_path / ".agents/skills/draft-agent-connector/SKILL.md").is_file()


def test_install_in_user_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    result = CliRunner().invoke(
        app, ["skills", "install", "draft-agent-connector", "--harness", "claude", "--scope", "user"]
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".claude/skills/draft-agent-connector/SKILL.md").is_file()


def test_existing_skill_requires_force(tmp_path: Path) -> None:
    runner = CliRunner()
    args = ["skills", "install", "draft-agent-connector", "--harness", "claude", "--project", str(tmp_path)]
    assert runner.invoke(app, args).exit_code == 0
    target = tmp_path / ".claude/skills/draft-agent-connector/SKILL.md"
    target.write_text("local changes")

    conflict = runner.invoke(app, args)
    assert conflict.exit_code == 1
    assert target.read_text() == "local changes"
    assert runner.invoke(app, [*args, "--force"]).exit_code == 0
    assert target.read_text() != "local changes"


@pytest.mark.parametrize(
    "arguments",
    [
        ["skills", "install", "unknown", "--harness", "claude"],
        ["skills", "install", "--harness", "claude"],
        ["skills", "install", "draft-agent-connector"],
        ["skills", "install", "draft-agent-connector", "--all", "--harness", "claude"],
        ["skills", "install", "draft-agent-connector", "--harness", "claude", "--scope", "user", "--project", "."],
    ],
)
def test_invalid_install_does_not_write(tmp_path: Path, arguments: list[str]) -> None:
    result = CliRunner().invoke(app, arguments, catch_exceptions=False)
    assert result.exit_code != 0
    assert not list(tmp_path.iterdir())
