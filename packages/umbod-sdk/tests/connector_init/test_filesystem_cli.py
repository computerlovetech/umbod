import importlib
import os
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from umbod_sdk.cli import app
from umbod_sdk.connector_init import (
    ConnectorInitializer,
    FilesystemProjectFiles,
    InitError,
    InitRequest,
)
from umbod_sdk.connector_init import cli as init_cli
from umbod_sdk.connector_init.adapters import InMemoryProjectFiles
from umbod_sdk.connectors.plugin_api import ConfigurationCheckResult

from .test_service import METADATA


@pytest.fixture
def project(tmp_path: Path) -> Path:
    package = tmp_path / "src" / "my_package"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (tmp_path / "pyproject.toml").write_bytes(METADATA)
    return tmp_path


def _tree(project: Path) -> dict[str, bytes | None]:
    return {
        str(path.relative_to(project)): None if path.is_dir() else path.read_bytes()
        for path in project.rglob("*")
    }


def test_cli_preview_does_not_write_and_check_accepts_applied_metadata(project: Path) -> None:
    runner = CliRunner()
    args = ["connectors", "init", "--name", "my-connector", "--module", "my_package.hello_world", "--project", str(project)]
    (project / "uv.lock").write_bytes(b"locked dependency bytes\n")
    before = _tree(project)
    preview = runner.invoke(app, args)
    assert preview.exit_code == 0, preview.output
    assert "Preview only" in preview.output
    assert "plugin = connector" in preview.output
    assert _tree(project) == before
    applied = runner.invoke(app, [*args, "--apply"])
    assert applied.exit_code == 0, applied.output
    assert "Applied connector initialization" in applied.output
    assert (project / "uv.lock").read_bytes() == b"locked dependency bytes\n"
    assert (project / "pyproject.toml").read_bytes().startswith(METADATA)
    checked = runner.invoke(app, ["connectors", "check", "--project", str(project)])
    assert checked.exit_code == 0, checked.output


def test_cli_defaults_to_current_project(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(project)
    result = CliRunner().invoke(app, ["connectors", "init", "--name", "my-connector", "--module", "my_package.hello_world"])
    assert result.exit_code == 0, result.output
    assert "Preview only" in result.output
    assert not (project / "src/my_package/hello_world.py").exists()


def test_cli_refusal_leaves_recursive_tree_unchanged(project: Path) -> None:
    (project / "uv.lock").write_bytes(b"lock\n")
    before = _tree(project)
    result = CliRunner().invoke(app, ["connectors", "init", "--name", "Bad", "--module", "my_package.hello_world", "--project", str(project), "--apply"])
    assert result.exit_code == 1
    assert _tree(project) == before


def test_cli_malformed_hatch_table_fails_without_traceback(project: Path) -> None:
    metadata = METADATA.split(b"[tool.hatch.build.targets.wheel]")[0] + b'[tool.hatch.build]\ntargets = "scalar"\n'
    (project / "pyproject.toml").write_bytes(metadata)
    result = CliRunner().invoke(app, ["connectors", "init", "--name", "my-connector", "--module", "my_package.hello_world", "--project", str(project)])
    assert result.exit_code == 1, result.output
    assert "[tool.hatch.build.targets] must be a table" in result.output
    assert "Traceback" not in result.output


def test_repeated_apply_refuses_without_overwrite(project: Path) -> None:
    args = ["connectors", "init", "--name", "my-connector", "--module", "my_package.hello_world", "--project", str(project), "--apply"]
    runner = CliRunner()
    assert runner.invoke(app, args).exit_code == 0
    before = _tree(project)
    repeated = runner.invoke(app, args)
    assert repeated.exit_code == 1
    assert _tree(project) == before


def test_cli_apply_error_displays_plan_before_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class DeniedFiles(InMemoryProjectFiles):
        def append_metadata(self, request: InitRequest, expected: bytes, addition: bytes) -> None:
            raise PermissionError("write denied")

    files = DeniedFiles(METADATA, "my_package")
    monkeypatch.setattr(init_cli, "create_initializer", lambda: ConnectorInitializer(files))
    result = CliRunner().invoke(app, ["connectors", "init", "--name", "my-connector", "--module", "my_package.hello_world", "--apply"])
    assert result.exit_code == 1
    assert "Planned source" in result.output
    assert "Planned addition" in result.output
    assert "write denied" in result.output
    assert "Applied connector initialization" not in result.output
    assert files.modules["my_package.hello_world"].endswith(b"plugin = connector\n")


def test_generated_public_contract_greets_ada(project: Path) -> None:
    request = InitRequest(project_directory=str(project), name="my-connector", module="my_package.hello_world")
    initializer = ConnectorInitializer(FilesystemProjectFiles())
    initializer.apply(initializer.plan(request))
    sys.path.insert(0, str(project / "src"))
    try:
        generated = importlib.import_module("my_package.hello_world")
        assert generated.plugin.id == "my-connector"
        assert generated.plugin.capability_description
        assert generated.check_configuration(generated.HelloWorldConfiguration()) == ConfigurationCheckResult(valid=True)
        assert generated.say_hello("Ada", generated.HelloWorldConfiguration()) == "Hello, Ada!"
    finally:
        sys.path.remove(str(project / "src"))
        sys.modules.pop("my_package.hello_world", None)
        sys.modules.pop("my_package", None)


def test_missing_metadata_is_refused(project: Path) -> None:
    (project / "pyproject.toml").unlink()
    request = InitRequest(project_directory=str(project), name="my-connector", module="my_package.hello_world")
    with pytest.raises(InitError, match="Cannot inspect"):
        ConnectorInitializer(FilesystemProjectFiles()).plan(request)


def test_concurrent_metadata_append_does_not_overwrite_existing_bytes(project: Path) -> None:
    class ConcurrentFiles(FilesystemProjectFiles):
        def _append(self, descriptor: int, addition: bytes) -> None:
            os.write(descriptor, b"# concurrent\n")
            super()._append(descriptor, addition)

    request = InitRequest(project_directory=str(project), name="my-connector", module="my_package.hello_world")
    initializer = ConnectorInitializer(ConcurrentFiles())
    with pytest.raises(InitError, match="changed during append"):
        initializer.apply(initializer.plan(request))
    metadata = (project / "pyproject.toml").read_bytes()
    assert metadata.startswith(METADATA + b"# concurrent\n")
    assert b'my-connector = "my_package.hello_world:plugin"' in metadata
    assert (project / "src/my_package/hello_world.py").exists()


def test_symlink_swap_before_creation_does_not_write_outside(project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    original_open = os.open
    swapped = False

    def swap_open(path: str | bytes | os.PathLike[str] | os.PathLike[bytes], flags: int, mode: int = 0o777, *, dir_fd: int | None = None) -> int:
        nonlocal swapped
        if path == "src" and not swapped:
            swapped = True
            (project / "src").rename(project / "old_src")
            (project / "src").symlink_to(outside, target_is_directory=True)
        if dir_fd is None:
            return original_open(path, flags, mode)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    request = InitRequest(project_directory=str(project), name="my-connector", module="my_package.hello_world")
    initializer = ConnectorInitializer(FilesystemProjectFiles())
    plan = initializer.plan(request)
    monkeypatch.setattr(os, "open", swap_open)
    with pytest.raises(InitError):
        initializer.apply(plan)
    assert list(outside.iterdir()) == []


def test_symlinked_module_and_package_are_refused(project: Path, tmp_path: Path) -> None:
    target = tmp_path / "unrelated"
    target.write_text("untouched")
    (project / "src/my_package/hello_world.py").symlink_to(target)
    request = InitRequest(project_directory=str(project), name="my-connector", module="my_package.hello_world")
    with pytest.raises(InitError, match="symlinked"):
        ConnectorInitializer(FilesystemProjectFiles()).plan(request)
    assert target.read_text() == "untouched"


def test_symlinked_metadata_is_refused(project: Path, tmp_path: Path) -> None:
    target = tmp_path / "metadata"
    target.write_bytes(METADATA)
    (project / "pyproject.toml").unlink()
    (project / "pyproject.toml").symlink_to(target)
    request = InitRequest(project_directory=str(project), name="my-connector", module="my_package.hello_world")
    with pytest.raises(InitError, match="symlinked"):
        ConnectorInitializer(FilesystemProjectFiles()).plan(request)
    assert target.read_bytes() == METADATA


def test_existing_same_name_directory_is_refused(project: Path) -> None:
    (project / "src/my_package/hello_world").mkdir()
    request = InitRequest(project_directory=str(project), name="my-connector", module="my_package.hello_world")
    with pytest.raises(InitError, match="already exists"):
        ConnectorInitializer(FilesystemProjectFiles()).plan(request)


def test_metadata_change_after_plan_is_refused(project: Path) -> None:
    request = InitRequest(project_directory=str(project), name="my-connector", module="my_package.hello_world")
    initializer = ConnectorInitializer(FilesystemProjectFiles())
    plan = initializer.plan(request)
    (project / "pyproject.toml").write_bytes(METADATA + b"# later\n")
    with pytest.raises(InitError, match="changed"):
        initializer.apply(plan)
    assert not (project / "src/my_package/hello_world.py").exists()
