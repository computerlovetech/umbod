import runpy
import shlex
import subprocess
import sys
from pathlib import Path


def test_image_build_generates_importable_release_identity_before_install(tmp_path: Path) -> None:
    dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile"
    instructions = dockerfile.read_text().splitlines()
    stamp = next(line for line in instructions if line.startswith("RUN python -c "))
    install = next(line for line in instructions if line.startswith("RUN uv sync") and "--no-editable" in line)
    assert instructions.index(stamp) < instructions.index(install)
    arguments = shlex.split(stamp.removeprefix("RUN "))
    destination = tmp_path / "umbod/api/src/umbod/build_identity.py"
    destination.parent.mkdir(parents=True)
    subprocess.run([sys.executable, "-c", arguments[2], "1.2.3", "abc123"], cwd=tmp_path, check=True)
    generated = runpy.run_path(str(destination))
    assert generated["UMBOD_RELEASE"] == "1.2.3"
    assert generated["UMBOD_REVISION"] == "abc123"
