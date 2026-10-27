from pathlib import Path
from typing import Dict, List, Union

import pytest
import yaml


WORKFLOWS = Path(__file__).resolve().parents[3] / ".github" / "workflows"


def test_harness_linting_is_reusable_and_runs_okf_checker() -> None:
    workflow = yaml.load((WORKFLOWS / "harness-linting.yml").read_text(), Loader=yaml.BaseLoader)
    assert "workflow_call" in workflow["on"]
    steps = workflow["jobs"]["harness-linting"]["steps"]
    assert any(step.get("run") == "python skills/development/write-module-readme/scripts/check_module_readmes.py ." for step in steps)
    assert any(
        step.get("run") == "python -m pip install -r skills/development/write-module-readme/requirements.txt"
        for step in steps
    )
    assert any(step.get("run") == "python skills/development/write-module-readme/scripts/check_readme_links.py ." for step in steps)
    assert any(step.get("run") == "python skills/development/write-module-readme/scripts/check_readme_bodies.py ." for step in steps)
    requirements = (WORKFLOWS.parents[1] / "skills/development/write-module-readme/requirements.txt").read_text()
    assert "PyYAML" in requirements
    assert "markdown-it-py" in requirements


@pytest.mark.parametrize("filename", ["umbod-ci.yml", "website-ci.yml"])
def test_ci_jobs_wait_for_harness_linting(filename: str) -> None:
    workflow = yaml.load((WORKFLOWS / filename).read_text(), Loader=yaml.BaseLoader)
    jobs = workflow["jobs"]
    assert jobs["harness-linting"]["uses"] == "./.github/workflows/harness-linting.yml"
    dependencies: Dict[str, Union[str, List[str]]] = {
        name: job.get("needs", []) for name, job in jobs.items()
    }
    gated = {"harness-linting"}
    while True:
        newly_gated = {
            name
            for name, needs in dependencies.items()
            if needs and set([needs] if isinstance(needs, str) else needs).issubset(gated)
        } - gated
        if not newly_gated:
            break
        gated.update(newly_gated)
    assert set(jobs) == gated


@pytest.mark.parametrize("filename", ["umbod-ci.yml", "website-ci.yml"])
def test_ci_runs_when_harness_workflow_changes(filename: str) -> None:
    workflow = yaml.load((WORKFLOWS / filename).read_text(), Loader=yaml.BaseLoader)
    assert ".github/workflows/harness-linting.yml" in workflow["on"]["pull_request"]["paths"]


@pytest.mark.parametrize("filename", ["umbod-ci.yml", "website-ci.yml"])
def test_skill_source_changes_trigger_ci(filename: str) -> None:
    workflow = yaml.load((WORKFLOWS / filename).read_text(), Loader=yaml.BaseLoader)
    assert "skills/development/write-module-readme/**" in workflow["on"]["pull_request"]["paths"]
    if filename == "website-ci.yml":
        assert "skills/development/write-module-readme/**" in workflow["on"]["push"]["paths"]


def test_readmes_anywhere_in_repository_trigger_ci() -> None:
    workflow = yaml.load((WORKFLOWS / "umbod-ci.yml").read_text(), Loader=yaml.BaseLoader)
    assert "**/README.md" in workflow["on"]["pull_request"]["paths"]
