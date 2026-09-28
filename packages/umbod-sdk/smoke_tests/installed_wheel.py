import importlib
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import umbod_sdk
from umbod_sdk.connectors.plugin_api import ConfigurationCheckResult


def invoke(project: Path, arguments: list[str], expected_code: int) -> str:
    result = subprocess.run(
        [str(Path(sys.executable).with_name("umbod")), "connectors", *arguments, "--project", str(project)],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == expected_code, result.stdout + result.stderr
    return result.stdout + result.stderr


def verify_project(project: Path) -> None:
    package = project / "src" / "wheel_smoke_connector"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (project / "pyproject.toml").write_text(
        '[project]\nname = "wheel-smoke-connector"\nversion = "0.1.0"\n'
        'requires-python = ">=3.14"\ndependencies = ["umbod>=0.1.0,<0.2.0"]\n'
        '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
        '[tool.hatch.build.targets.wheel]\npackages = ["src/wheel_smoke_connector"]\n'
    )
    (project / "uv.lock").write_text("unchanged lock sentinel")
    arguments = ["init", "--name", "wheel-smoke", "--module", "wheel_smoke_connector.hello_world"]
    before = (project / "pyproject.toml").read_bytes()
    assert "Preview only" in invoke(project, arguments, 0)
    assert (project / "pyproject.toml").read_bytes() == before
    assert not (package / "hello_world.py").exists()
    assert "Applied" in invoke(project, [*arguments, "--apply"], 0)
    invoke(project, ["check"], 0)
    assert "image not verified" in invoke(project, ["check", "--sdk-version", "0.1.0"], 0)
    assert "does not accept" in invoke(project, ["check", "--sdk-version", "0.2.0"], 1)
    assert (project / "uv.lock").read_text() == "unchanged lock sentinel"
    sys.path.insert(0, str(project / "src"))
    generated = importlib.import_module("wheel_smoke_connector.hello_world")
    configuration = generated.HelloWorldConfiguration()
    assert generated.say_hello("Ada", configuration) == "Hello, Ada!"
    assert generated.plugin.registration()["configuration_check"](configuration).valid is True


def main() -> None:
    assert Path(umbod_sdk.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    assert ConfigurationCheckResult.valid().valid is True
    assert ConfigurationCheckResult.invalid("Invalid credentials").valid is False
    with TemporaryDirectory() as directory:
        verify_project(Path(directory).resolve())


if __name__ == "__main__":
    main()
