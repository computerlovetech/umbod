from __future__ import annotations

import argparse
import re
import tomllib
from collections.abc import Sequence
from pathlib import Path

from scripts.release_versions import ReleaseVersion


def stamp_versions(project_text: str, lock_text: str, version: str) -> tuple[str, str]:
    selected = ReleaseVersion.parse(version)
    if version != selected.pep440():
        raise ValueError(f"SDK version must use PEP 440 spelling: {version}")
    try:
        project = tomllib.loads(project_text)
        lock = tomllib.loads(lock_text)
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"Invalid SDK project or API lock TOML: {error}") from error
    project_data = project.get("project", {})
    if not isinstance(project_data, dict):
        raise TypeError("SDK project section must be a table")
    if project_data.get("name") != "umbod" or "version" not in project_data:
        raise ValueError("SDK project must contain umbod name and version")
    if not isinstance(project_data["version"], str):
        raise TypeError("SDK project version must be a string")
    lock_packages = lock.get("package", [])
    if not isinstance(lock_packages, list) or any(not isinstance(package, dict) for package in lock_packages):
        raise TypeError("API lock package entries must be tables")
    packages = [package for package in lock_packages if package.get("name") == "umbod"]
    if len(packages) != 1 or packages[0].get("source") != {"editable": "../../packages/umbod-sdk"}:
        raise ValueError("API lock must contain exactly one local editable umbod SDK package")
    if "version" not in packages[0]:
        raise ValueError("API lock SDK package must contain a version")
    if not isinstance(packages[0]["version"], str):
        raise TypeError("API lock SDK package version must be a string")
    project_pattern = re.compile(r'(?ms)^(\[project\]\r?\n)(.*?)(?=^\[|\Z)')
    lock_pattern = re.compile(r'(?ms)^(\[\[package\]\]\r?\n)(.*?)(?=^\[|\Z)')

    def replace_field(section: str, old: str, field: str) -> str:
        pattern = re.compile(rf'(?m)^{field} = "{re.escape(old)}"(?=\r?$)')
        replaced, count = pattern.subn(f'{field} = "{version}"', section)
        if count != 1:
            raise ValueError(f"Expected exactly one {field} field in SDK section")
        return replaced

    def replace_project(match: re.Match[str]) -> str:
        return match.group(1) + replace_field(match.group(2), project["project"]["version"], "version")

    updated_project, project_count = project_pattern.subn(replace_project, project_text)
    if project_count != 1:
        raise ValueError("Expected exactly one [project] section")

    def replace_package(match: re.Match[str]) -> str:
        section = match.group(2)
        if not re.search(r'(?m)^name = "umbod"(?=\r?$)', section):
            return match.group(0)
        return match.group(1) + replace_field(section, packages[0]["version"], "version")

    updated_lock, lock_count = lock_pattern.subn(replace_package, lock_text)
    if lock_count != len(lock_packages):
        raise ValueError("Malformed API lock package sections")
    if tomllib.loads(updated_project)["project"]["version"] != version:
        raise ValueError("SDK project version stamp failed")
    stamped_packages = [package for package in tomllib.loads(updated_lock)["package"] if package["name"] == "umbod"]
    if len(stamped_packages) != 1 or stamped_packages[0]["version"] != version:
        raise ValueError("API lock SDK version stamp failed")
    return updated_project, updated_lock


def stamp_files(project_path: Path, lock_path: Path, version: str) -> None:
    project_text, lock_text = stamp_versions(
        project_path.read_bytes().decode("utf-8"), lock_path.read_bytes().decode("utf-8"), version
    )
    project_path.write_bytes(project_text.encode("utf-8"))
    lock_path.write_bytes(lock_text.encode("utf-8"))


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("lock", type=Path)
    parser.add_argument("version")
    options = parser.parse_args(arguments)
    stamp_files(options.project, options.lock, options.version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
