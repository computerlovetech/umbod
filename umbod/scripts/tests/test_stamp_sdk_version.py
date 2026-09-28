from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from scripts.stamp_sdk_version import stamp_files, stamp_versions

PROJECT = '[project]\nname = "umbod"\nversion = "0.1.0"\n\n[tool.uv]\nmanaged = true\n'
LOCK = 'version = 1\n\n[[package]]\nname = "other"\nversion = "2.0.0"\n\n[[package]]\nname = "umbod"\nversion = "0.1.0"\nsource = { editable = "../../packages/umbod-sdk" }\n\n[[package]]\nname = "umbod-core"\nversion = "0.0.1b2"\n'


def test_stamp_preserves_unrelated_project_and_lock_bytes() -> None:
    project, lock = stamp_versions(PROJECT, LOCK, "1.2.3b4")
    assert project == PROJECT.replace('version = "0.1.0"', 'version = "1.2.3b4"')
    assert lock == LOCK.replace('name = "umbod"\nversion = "0.1.0"', 'name = "umbod"\nversion = "1.2.3b4"')


def test_stamp_real_core_lock_preserves_other_packages() -> None:
    root = Path(__file__).resolve().parents[3]
    project = (root / "packages/umbod-sdk/pyproject.toml").read_text()
    lock = (root / "umbod/api/uv.lock").read_text()
    stamped_project, stamped_lock = stamp_versions(project, lock, "4.2.1b2")
    original_packages = tomllib.loads(lock)["package"]
    stamped_packages = tomllib.loads(stamped_lock)["package"]
    assert [package for package in original_packages if package["name"] != "umbod"] == [
        package for package in stamped_packages if package["name"] != "umbod"
    ]
    assert tomllib.loads(stamped_project)["project"]["version"] == "4.2.1b2"


@pytest.mark.parametrize(
    ("project", "lock", "error"),
    [
        ("[project\n", LOCK, "Invalid"),
        (PROJECT, LOCK.replace('name = "umbod"', 'name = "absent"'), "exactly one"),
        (PROJECT, LOCK + '\n[[package]]\nname = "umbod"\nversion = "0.1.0"\n', "exactly one"),
        (PROJECT, LOCK.replace('../../packages/umbod-sdk', '../other'), "local editable"),
    ],
)
def test_stamp_rejects_malformed_or_ambiguous_input(project: str, lock: str, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        stamp_versions(project, lock, "1.0.0")


@pytest.mark.parametrize(
    ("project", "lock", "error"),
    [
        ('project = "invalid"\n', LOCK, "SDK project section"),
        (PROJECT, 'package = ["invalid"]\n', "API lock package entries"),
        (PROJECT, 'package = [42]\n', "API lock package entries"),
        (PROJECT.replace('version = "0.1.0"', "version = 12"), LOCK, "SDK project version"),
        (PROJECT, LOCK.replace('name = "umbod"\nversion = "0.1.0"', 'name = "umbod"\nversion = 12'), "API lock SDK package version"),
    ],
)
def test_stamp_rejects_invalid_toml_shapes(project: str, lock: str, error: str) -> None:
    with pytest.raises(TypeError, match=error):
        stamp_versions(project, lock, "1.0.0")


def test_stamp_files_preserves_crlf_bytes(tmp_path: Path) -> None:
    project_path = tmp_path / "pyproject.toml"
    lock_path = tmp_path / "uv.lock"
    project_path.write_bytes(PROJECT.replace("\n", "\r\n").encode("utf-8"))
    lock_path.write_bytes(LOCK.replace("\n", "\r\n").encode("utf-8"))
    stamp_files(project_path, lock_path, "1.2.3b4")
    assert project_path.read_bytes() == PROJECT.replace('version = "0.1.0"', 'version = "1.2.3b4"').replace("\n", "\r\n").encode("utf-8")
    assert lock_path.read_bytes() == LOCK.replace('name = "umbod"\nversion = "0.1.0"', 'name = "umbod"\nversion = "1.2.3b4"').replace("\n", "\r\n").encode("utf-8")


def test_stamp_rejects_semver_sdk_version() -> None:
    with pytest.raises(ValueError, match="PEP 440"):
        stamp_versions(PROJECT, LOCK, "1.0.0-beta.2")
