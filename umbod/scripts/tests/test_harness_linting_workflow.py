from pathlib import Path
from typing import Dict, List, Union

import pytest
import yaml


WORKFLOWS = Path(__file__).resolve().parents[3] / ".github" / "workflows"


def test_harness_linting_is_reusable_and_runs_okf_checker() -> None:
    workflow = yaml.load((WORKFLOWS / "harness-linting.yml").read_text(), Loader=yaml.BaseLoader)
    assert "workflow_call" in workflow["on"]
    steps = workflow["jobs"]["harness-linting"]["steps"]
    assert any(step.get("run") == "python umbod/scripts/check_module_readmes.py" for step in steps)
    assert any("PyYAML" in step.get("run", "") for step in steps)


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


def test_module_readmes_in_any_src_tree_trigger_ci() -> None:
    workflow = yaml.load((WORKFLOWS / "umbod-ci.yml").read_text(), Loader=yaml.BaseLoader)
    assert "**/src/**/README.md" in workflow["on"]["pull_request"]["paths"]
