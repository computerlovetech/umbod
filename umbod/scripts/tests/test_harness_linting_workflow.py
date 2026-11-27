import fnmatch
import os
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[3] / ".github" / "workflows"


def test_harness_linting_is_reusable_and_runs_okf_checker() -> None:
    workflow = yaml.load(
        (WORKFLOWS / "harness-linting.yml").read_text(), Loader=yaml.BaseLoader
    )
    assert "workflow_call" in workflow["on"]
    steps = workflow["jobs"]["harness-linting"]["steps"]
    assert any(
        step.get("run")
        == "python skills/development/write-module-readme/scripts/check_module_readmes.py ."
        for step in steps
    )
    assert any(
        step.get("run")
        == "python -m pip install -r skills/development/write-module-readme/requirements.txt"
        for step in steps
    )
    assert any(
        step.get("run")
        == "python skills/development/write-module-readme/scripts/check_readme_links.py ."
        for step in steps
    )
    assert any(
        step.get("run")
        == "python skills/development/write-module-readme/scripts/check_readme_bodies.py ."
        for step in steps
    )
    requirements = (
        WORKFLOWS.parents[1] / "skills/development/write-module-readme/requirements.txt"
    ).read_text()
    assert "PyYAML" in requirements
    assert "markdown-it-py" in requirements


def test_harness_linting_validates_all_skills_and_tests_the_validator() -> None:
    workflow = yaml.load(
        (WORKFLOWS / "harness-linting.yml").read_text(), Loader=yaml.BaseLoader
    )
    commands = {
        step.get("run") for step in workflow["jobs"]["harness-linting"]["steps"]
    }
    assert (
        "python skills/development/write-skill/scripts/validate_skill.py skills"
        in commands
    )
    assert (
        "python -m unittest discover -s skills/development/write-skill/tests"
        in commands
    )


def _run_project_directory_check(
    workspace: Path, extra_allowed_folder: str = "",
) -> subprocess.CompletedProcess[str]:
    workflow = yaml.load(
        (WORKFLOWS / "harness-linting.yml").read_text(), Loader=yaml.BaseLoader
    )
    step = next(
        step for step in workflow["jobs"]["harness-linting"]["steps"]
        if step.get("name") == "Validate project directory contents"
    )
    env = {**os.environ, **step["env"]}
    if extra_allowed_folder:
        env["ALLOWED_PROJECT_FOLDERS"] += f"\n{extra_allowed_folder}\n"
    return subprocess.run(
        ["bash", "-e", "-c", step["run"]], cwd=workspace, env=env,
        capture_output=True, text=True, check=False,
    )


def test_project_directory_check_allows_contents_inside_allowed_folders(tmp_path: Path) -> None:
    records = tmp_path / "umbod/project/architecture-records"
    records.mkdir(parents=True)
    (records / "index.md").touch()

    result = _run_project_directory_check(tmp_path)

    assert result.returncode == 0, result.stderr


def test_project_directory_check_accepts_additional_configured_folders(tmp_path: Path) -> None:
    project = tmp_path / "umbod/project"
    (project / "architecture-records").mkdir(parents=True)
    (project / "additional-records").mkdir()

    result = _run_project_directory_check(tmp_path, "additional-records")

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("entry_name", "entry_type"),
    [("notes.md", "file"), (".hidden", "directory"), ("architecture-records", "file"), ("architecture-records", "symlink")],
)
def test_project_directory_check_rejects_unexpected_entries(
    tmp_path: Path, entry_name: str, entry_type: str,
) -> None:
    project = tmp_path / "umbod/project"
    project.mkdir(parents=True)
    entry = project / entry_name
    if entry_type == "file":
        entry.touch()
    elif entry_type == "directory":
        entry.mkdir()
    else:
        entry.symlink_to(tmp_path, target_is_directory=True)

    result = _run_project_directory_check(tmp_path)

    assert result.returncode == 1
    assert f"umbod/project/{entry_name}" in result.stderr


def test_ci_jobs_wait_for_harness_linting() -> None:
    workflow = yaml.load(
        (WORKFLOWS / "umbod-ci.yml").read_text(), Loader=yaml.BaseLoader
    )
    jobs = workflow["jobs"]
    assert jobs["harness-linting"]["uses"] == "./.github/workflows/harness-linting.yml"
    dependencies: dict[str, str | list[str]] = {
        name: job.get("needs", []) for name, job in jobs.items()
    }
    gated = {"harness-linting"}
    while True:
        newly_gated = {
            name
            for name, needs in dependencies.items()
            if needs
            and set([needs] if isinstance(needs, str) else needs).issubset(gated)
        } - gated
        if not newly_gated:
            break
        gated.update(newly_gated)
    assert set(jobs) == gated


def test_ci_runs_when_harness_workflow_changes() -> None:
    workflow = yaml.load(
        (WORKFLOWS / "umbod-ci.yml").read_text(), Loader=yaml.BaseLoader
    )
    assert any(
        fnmatch.fnmatchcase(".github/workflows/harness-linting.yml", pattern)
        for pattern in workflow["on"]["pull_request"]["paths"]
    )


def test_skill_source_changes_trigger_ci() -> None:
    workflow = yaml.load(
        (WORKFLOWS / "umbod-ci.yml").read_text(), Loader=yaml.BaseLoader
    )
    assert any(
        fnmatch.fnmatchcase("skills/development/write-module-readme/SKILL.md", pattern)
        for pattern in workflow["on"]["pull_request"]["paths"]
    )


def test_readmes_anywhere_in_repository_trigger_ci() -> None:
    workflow = yaml.load(
        (WORKFLOWS / "umbod-ci.yml").read_text(), Loader=yaml.BaseLoader
    )
    assert "**/README.md" in workflow["on"]["pull_request"]["paths"]
