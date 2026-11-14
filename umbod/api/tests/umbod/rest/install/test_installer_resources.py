import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest

from umbod.core.harness_plugins.ports import ScriptKind
from umbod.rest.install import resources
from umbod.rest.install.resources import BundledInstallerSourceReader


@pytest.mark.parametrize("kind", ["sh", "ps1"])
def test_editable_installer_resources_match_canonical_source(kind: ScriptKind) -> None:
    root = Path(__file__).resolve().parents[4]
    source = root / f"src/umbod/rest/install/assets/install.{kind}"
    assert BundledInstallerSourceReader().read(kind).text.encode("utf-8") == source.read_bytes()


@pytest.mark.parametrize("content", [b"\xff", b"", ("ø" * 131073).encode("utf-8")])
def test_invalid_or_oversized_resource_is_rejected_before_rendering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: bytes,
) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "install.sh").write_bytes(content)

    def package_directory(package: str) -> Path:
        return tmp_path

    monkeypatch.setattr(resources, "files", package_directory)
    with pytest.raises(ValueError):
        BundledInstallerSourceReader().read("sh")


def test_wheel_contains_exact_canonical_installer_sources(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[4]
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=root, capture_output=True, text=True, check=True, timeout=120,
    )
    wheel, = tmp_path.glob("umbod_core-*.whl")
    with ZipFile(wheel) as archive:
        for kind in ("sh", "ps1"):
            resource = f"umbod/rest/install/assets/install.{kind}"
            assert archive.read(resource) == (root / "src" / resource).read_bytes()
