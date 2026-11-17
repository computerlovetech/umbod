import fnmatch
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml


REPOSITORY = Path(__file__).resolve().parents[3]
COMPONENT_JOBS = {
    "docs": "website",
    "sdk-tests": "sdk",
    "backend-tests": "backend",
    "script-tests": "scripts",
    "plugin-installers": "installers",
    "core": "core",
    "connector-builder": "connector",
    "frontend": "frontend",
    "helm": "helm",
    "helm-kubernetes-schema": "helm",
    "helm-kind-install": "kind",
}


@pytest.fixture
def workflow() -> dict[str, Any]:
    return yaml.load(
        (REPOSITORY / ".github/workflows/umbod-ci.yml").read_text(), Loader=yaml.BaseLoader
    )


@pytest.fixture
def filters() -> dict[str, list[str]]:
    return yaml.safe_load((REPOSITORY / ".github/ci-paths.yml").read_text())


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("umbod/docs/index.md", {"website"}),
        ("website/index.html", {"website"}),
        ("release-metadata.json", {"website"}),
        ("umbod/frontend/src/routes/+page.svelte", {"frontend", "kind"}),
        ("umbod/frontend/src/lib/styles/admin.css", {"backend", "frontend", "kind"}),
        ("website/public/umbod-logo.svg", {"backend", "website"}),
        ("umbod/api/src/umbod/core/service.py", {"backend", "core", "kind"}),
        ("umbod/api/tests/umbod/core/test_service.py", {"backend"}),
        ("packages/umbod-sdk/src/umbod_sdk/connectors/api.py", {"sdk", "backend", "core", "connector", "kind"}),
        ("umbod/api/src/umbod/rest/install/assets/install.ps1", {"backend", "core", "kind", "installers"}),
        ("umbod/docker-compose.yml", {"backend"}),
        ("umbod/frontend/deployment/generate-config.sh", {"backend", "frontend", "kind"}),
        ("umbod/scripts/tests/test_plugin_installers_windows.py", {"scripts", "installers"}),
        ("umbod/scripts/tests/test_release_versions.py", {"scripts", "website"}),
        ("umbod/deploy/helm/umbod/values.yaml", {"helm", "kind", "website"}),
        (".dockerignore", {"core", "connector", "kind"}),
        ("umbod/README.md", set()),
    ],
)
def test_changed_inputs_select_only_their_consumers(
    workflow: dict[str, Any], filters: dict[str, list[str]], path: str, expected: set[str]
) -> None:
    selected = {
        component
        for component, patterns in filters.items()
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)
    }
    assert selected == expected
    if selected:
        assert any(fnmatch.fnmatchcase(path, pattern) for pattern in workflow["on"]["pull_request"]["paths"])


@pytest.mark.parametrize("path", [".github/ci-paths.yml", ".github/workflows/umbod-ci.yml", ".github/workflows/website-ci.yml"])
def test_pipeline_changes_select_every_component(
    workflow: dict[str, Any], filters: dict[str, list[str]], path: str
) -> None:
    assert all(any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns) for patterns in filters.values())
    assert any(fnmatch.fnmatchcase(path, pattern) for pattern in workflow["on"]["pull_request"]["paths"])


def test_main_pushes_always_produce_exact_commit_ci(workflow: dict[str, Any]) -> None:
    assert workflow["on"]["push"] == {"branches": ["main"]}
    for path in (".github/ci-paths.yml", ".dockerignore", "website/**", "release-metadata.json"):
        assert path in workflow["on"]["pull_request"]["paths"]


def test_component_jobs_use_the_published_change_selection(workflow: dict[str, Any]) -> None:
    jobs = workflow["jobs"]
    for name, component in COMPONENT_JOBS.items():
        assert jobs[name]["needs"] == "changes"
        assert jobs[name]["if"] == f"needs.changes.outputs.{component} == 'true'"
        assert component in jobs["changes"]["outputs"]
    assert jobs["changes"]["steps"][-1]["with"]["filters"] == ".github/ci-paths.yml"
    assert set(jobs["ci-complete"]["needs"]) == {*COMPONENT_JOBS, "changes", "harness-linting"}


@pytest.fixture
def job_results() -> dict[str, Any]:
    return {
        "harness-linting": {"result": "success"},
        "changes": {
            "result": "success",
            "outputs": {component: "false" for component in COMPONENT_JOBS.values()},
        },
        **{name: {"result": "skipped"} for name in COMPONENT_JOBS},
    }


def run_completion(workflow: dict[str, Any], job_results: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    command = workflow["jobs"]["ci-complete"]["steps"][0]["run"]
    return subprocess.run(
        ["bash", "-c", command],
        env={**os.environ, "JOB_RESULTS": json.dumps(job_results)},
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


@pytest.mark.parametrize("selected", [True, False])
def test_completion_accepts_successful_selected_jobs_and_intentional_skips(
    workflow: dict[str, Any], job_results: dict[str, Any], selected: bool
) -> None:
    if selected:
        job_results["changes"]["outputs"] = {component: "true" for component in COMPONENT_JOBS.values()}
        for name in COMPONENT_JOBS:
            job_results[name]["result"] = "success"
    result = run_completion(workflow, job_results)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("name", list(COMPONENT_JOBS))
@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped"])
def test_completion_rejects_selected_jobs_that_did_not_succeed(
    workflow: dict[str, Any], job_results: dict[str, Any], name: str, result: str
) -> None:
    component = COMPONENT_JOBS[name]
    job_results["changes"]["outputs"][component] = "true"
    for job, selected_component in COMPONENT_JOBS.items():
        if selected_component == component:
            job_results[job]["result"] = "success"
    job_results[name]["result"] = result
    assert run_completion(workflow, job_results).returncode != 0


@pytest.mark.parametrize("name", ["changes", "harness-linting"])
@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped"])
def test_completion_requires_successful_detection_and_harness_validation(
    workflow: dict[str, Any], job_results: dict[str, Any], name: str, result: str
) -> None:
    job_results[name]["result"] = result
    assert run_completion(workflow, job_results).returncode != 0


@pytest.mark.parametrize("selection", [None, "", "unknown"])
def test_completion_fails_closed_for_missing_or_invalid_selection(
    workflow: dict[str, Any], job_results: dict[str, Any], selection: str | None
) -> None:
    if selection is None:
        del job_results["changes"]["outputs"]["backend"]
    else:
        job_results["changes"]["outputs"]["backend"] = selection
    assert run_completion(workflow, job_results).returncode != 0


def test_publication_keeps_all_three_images_for_the_same_commit(workflow: dict[str, Any]) -> None:
    publication = workflow["jobs"]["publish-main-images"]
    assert publication["needs"] == ["ci-complete", "changes"]
    assert "needs.ci-complete.result == 'success'" in publication["if"]
    assert "github.event_name == 'push'" in publication["if"]
    for component in ("core", "frontend", "connector"):
        assert f"needs.changes.outputs.{component} == 'true'" in publication["if"]
    assert {entry["name"] for entry in publication["strategy"]["matrix"]["include"]} == {"core", "frontend", "connector-builder"}
    promotion = workflow["jobs"]["promote-nightly-images"]
    assert promotion["needs"] == "publish-main-images"
    assert "needs.publish-main-images.result == 'success'" in promotion["if"]


def test_sdk_tests_use_python_with_prebuilt_dependencies(workflow: dict[str, Any]) -> None:
    setup = next(step for step in workflow["jobs"]["sdk-tests"]["steps"] if step.get("uses") == "astral-sh/setup-uv@v7")
    assert setup["with"]["python-version"] == "3.14"
    assert setup["with"]["enable-cache"] == "true"


def test_script_tests_do_not_repeat_platform_or_website_owned_tests(workflow: dict[str, Any]) -> None:
    command = workflow["jobs"]["script-tests"]["steps"][-1]["run"]
    for filename in ("test_plugin_installers.py", "test_plugin_installers_windows.py", "test_release_versions.py", "test_release_workflow.py", "test_website_deployment.py"):
        assert f"--ignore=../scripts/tests/{filename}" in command
    assert not any("scripts/tests" in step.get("run", "") for step in workflow["jobs"]["backend-tests"]["steps"])
    assert not any("pytest" in step.get("run", "") for step in workflow["jobs"]["core"]["steps"])


def test_frontend_build_context_excludes_generated_coverage() -> None:
    ignored = (REPOSITORY / "umbod/frontend/.dockerignore").read_text().splitlines()
    assert "coverage" in ignored
