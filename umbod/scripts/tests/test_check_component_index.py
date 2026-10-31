import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from check_component_index import INDEX_PATH, local_destinations

SKILL = Path(__file__).resolve().parents[3] / "skills" / "frontend" / "reusable-components"
SCRIPT = SKILL / "scripts" / "check_component_index.py"


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("[Button](src/Button.svelte#props)", ["src/Button.svelte"]),
        ('[Button](src/Button.svelte?raw=1 "Button")', ["src/Button.svelte"]),
        ("[Button][control]\n\n[control]: src/Button.svelte", ["src/Button.svelte"]),
        ("[Button][]\n\n[Button]: src/Button.svelte", ["src/Button.svelte"]),
        ("[Button]\n\n[Button]: src/Button.svelte", ["src/Button.svelte"]),
        ("[File](<src/some file.svelte>)", ["src/some file.svelte"]),
        ("[File](src/some%20file.svelte)", ["src/some file.svelte"]),
        ("[File](src/file_(one).svelte)", ["src/file_(one).svelte"]),
        ("![Icon](static/icon.svg)", ["static/icon.svg"]),
        ('<a href="src/Button.svelte">Button</a><img src="static/icon.svg"/>', ["src/Button.svelte", "static/icon.svg"]),
        ("[Site](https://example.com) [Mail](mailto:a@example.com) [CDN](//example.com/a)", []),
        ("[Heading](#heading) [Query](?raw=1)", []),
        ("`[Code](missing.svelte)`\n\n```md\n[Code](missing.svelte)\n```", []),
        ("<!-- [Hidden](missing.svelte) -->", []),
        ("[A](src/Button.svelte) [B](src/Button.svelte)", ["src/Button.svelte"]),
    ],
)
def test_extracts_local_file_links_without_code_or_external_urls(content: str, expected: list[str]) -> None:
    assert local_destinations(content) == expected


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    (repository / INDEX_PATH).parent.mkdir(parents=True)
    return repository


def run_checker(repository: Path, working_directory: Path, script: Path = SCRIPT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), str(repository)],
        cwd=working_directory,
        check=False,
        capture_output=True,
        text=True,
    )


def test_cli_resolves_index_relative_and_repository_root_links(repository: Path, tmp_path: Path) -> None:
    component = repository / "umbod/frontend/src/Button with spaces.svelte"
    component.parent.mkdir()
    component.write_text("")
    (repository / INDEX_PATH).write_text(
        "[Relative](src/Button%20with%20spaces.svelte#props) "
        "[Root](/umbod/frontend/src/Button%20with%20spaces.svelte?raw=1) "
        "[Sources](src/)"
    )
    result = run_checker(repository, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "Component index link check passed" in result.stdout


def test_cli_reports_every_dead_link(repository: Path, tmp_path: Path) -> None:
    (repository / INDEX_PATH).write_text("[Deleted](src/Deleted.svelte) [Moved](src/Old.svelte)")
    result = run_checker(repository, tmp_path)
    assert result.returncode == 1
    assert "missing local target: src/Deleted.svelte" in result.stderr
    assert "missing local target: src/Old.svelte" in result.stderr


def test_cli_detects_a_component_deleted_after_a_successful_check(repository: Path, tmp_path: Path) -> None:
    component = repository / "umbod/frontend/Button.svelte"
    component.write_text("")
    (repository / INDEX_PATH).write_text("[Button](Button.svelte)")
    assert run_checker(repository, tmp_path).returncode == 0
    component.unlink()
    result = run_checker(repository, tmp_path)
    assert result.returncode == 1
    assert "missing local target: Button.svelte" in result.stderr


def test_cli_fails_when_index_is_missing(repository: Path, tmp_path: Path) -> None:
    result = run_checker(repository, tmp_path)
    assert result.returncode == 1
    assert "COMPONENT_INDEX.md: cannot check links" in result.stderr


def test_cli_fails_when_index_is_not_utf8(repository: Path, tmp_path: Path) -> None:
    (repository / INDEX_PATH).write_bytes(b"\xff")
    result = run_checker(repository, tmp_path)
    assert result.returncode == 1
    assert "cannot check links" in result.stderr


@pytest.mark.parametrize("content", ["", "# Components", "[External](https://example.com)"])
def test_cli_rejects_an_index_without_local_file_links(repository: Path, tmp_path: Path, content: str) -> None:
    (repository / INDEX_PATH).write_text(content)
    result = run_checker(repository, tmp_path)
    assert result.returncode == 1
    assert "no local file links found" in result.stderr


def test_cli_runs_from_a_copied_skill_installation(repository: Path, tmp_path: Path) -> None:
    installed = tmp_path / "installed-skill"
    shutil.copytree(SKILL, installed, ignore=shutil.ignore_patterns("__pycache__"))
    (repository / "umbod/frontend/Button.svelte").write_text("")
    (repository / INDEX_PATH).write_text("[Button](Button.svelte)")
    result = run_checker(repository, tmp_path, installed / "scripts/check_component_index.py")
    assert result.returncode == 0, result.stderr


def test_cli_requires_an_explicit_repository_root(tmp_path: Path) -> None:
    result = subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp_path, check=False, capture_output=True, text=True)
    assert result.returncode == 2
    assert "required: repository" in result.stderr


def test_cli_rejects_a_nonexistent_repository(tmp_path: Path) -> None:
    result = run_checker(tmp_path / "missing", tmp_path)
    assert result.returncode == 2
    assert "repository is not a directory" in result.stderr
