import fnmatch
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml


REPOSITORY = Path(__file__).resolve().parents[3]
COMPONENT_JOBS = {
    "docs": "website",
    "lint": "lint",
    "semgrep": "semgrep",
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
        ("umbod/frontend/src/routes/+page.svelte", {"frontend", "kind", "semgrep"}),
        ("umbod/frontend/src/lib/styles/admin.css", {"backend", "frontend", "kind", "semgrep"}),
        ("website/public/umbod-logo.svg", {"backend", "website"}),
        ("umbod/api/src/umbod/core/service.py", {"backend", "core", "kind", "lint", "semgrep"}),
        ("umbod/api/tests/umbod/core/test_service.py", {"backend", "lint", "semgrep"}),
        ("packages/umbod-sdk/src/umbod_sdk/connectors/api.py", {"sdk", "backend", "core", "connector", "kind", "lint", "semgrep"}),
        ("packages/umbod-sdk/tests/test_connector.py", {"sdk", "backend", "core", "connector", "kind", "lint", "semgrep"}),
        ("packages/umbod-sdk/pyproject.toml", {"sdk", "backend", "core", "connector", "kind", "scripts", "lint", "semgrep"}),
        ("packages/umbod-sdk/ruff.toml", {"sdk", "backend", "core", "connector", "kind", "lint", "semgrep"}),
        (".semgrep.yml", {"backend", "semgrep"}),
        (".semgrep/production-design.yml", {"backend", "semgrep"}),
        (".semgrep/test-correctness.yml", {"backend", "semgrep"}),
        (".semgrepignore", {"backend", "semgrep"}),
        ("pyproject.toml", {"lint"}),
        ("ruff.toml", {"lint"}),
        (".ruff.toml", {"lint"}),
        ("umbod/pyproject.toml", {"website", "semgrep"}),
        ("umbod/uv.lock", {"website", "semgrep"}),
        ("umbod/api/src/umbod/rest/install/assets/install.ps1", {"backend", "core", "kind", "installers", "lint", "semgrep"}),
        ("umbod/docker-compose.yml", {"backend"}),
        ("umbod/frontend/deployment/generate-config.sh", {"backend", "frontend", "kind", "semgrep"}),
        ("umbod/scripts/tests/test_plugin_installers_windows.py", {"scripts", "installers", "semgrep"}),
        ("umbod/scripts/tests/test_release_versions.py", {"scripts", "website", "semgrep"}),
        ("umbod/scripts/repository_check.py", {"scripts", "semgrep"}),
        ("umbod/tests/kind-runtime/fixtures/connector.py", {"semgrep"}),
        ("umbod/deploy/helm/umbod/values.yaml", {"helm", "kind", "website", "semgrep"}),
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


def test_full_recovery_overrides_path_filters_only_on_main_pushes(workflow: dict[str, Any]) -> None:
    changes = workflow["jobs"]["changes"]
    recovery, _, path_filter = changes["steps"]
    assert recovery["if"] == "github.event_name == 'push' && github.ref == 'refs/heads/main'"
    assert path_filter["if"] == "steps.recovery.outputs.full != 'true'"
    for component in COMPONENT_JOBS.values():
        assert changes["outputs"][component] == (
            f"${{{{ steps.recovery.outputs.full || steps.filter.outputs.{component} }}}}"
        )


@pytest.mark.parametrize(
    ("preceding_runs", "lookup_exit", "forced_push", "expected_output"),
    [
        ([(2, "preceding-commit", "success")], 0, "false", ""),
        ([(1, "preceding-commit", "success"), (2, "preceding-commit", "failure")], 0, "false", "full=true\n"),
        ([(1, "preceding-commit", "success"), (2, "preceding-commit", "cancelled")], 0, "false", "full=true\n"),
        ([(2, "preceding-commit", None)], 0, "false", "full=true\n"),
        ([], 0, "false", "full=true\n"),
        ([(2, "older-commit", "success")], 0, "false", "full=true\n"),
        ([(2, "preceding-commit", "success")], 1, "false", "full=true\n"),
        ([(2, "preceding-commit", "success")], 0, "true", "full=true\n"),
    ],
    ids=["green", "failed", "cancelled", "running", "first-run", "unverified-gap", "lookup-fails", "force-push"],
)
def test_main_push_falls_back_to_full_ci_without_confirmed_preceding_success(
    workflow: dict[str, Any],
    tmp_path: Path,
    preceding_runs: list[tuple[int, str, str | None]],
    lookup_exit: int,
    forced_push: str,
    expected_output: str,
) -> None:
    if not shutil.which("jq") or not shutil.which("timeout"):
        pytest.skip("Workflow history replay requires jq and timeout")
    workflow_runs = [
        {"run_number": number, "head_sha": sha, "conclusion": conclusion}
        for number, sha, conclusion in [(4, "preceding-commit", "success"), *preceding_runs]
    ]
    gh = tmp_path / "gh"
    gh.write_text(
        '#!/usr/bin/env bash\n'
        'if [[ "$LOOKUP_EXIT" != 0 ]]; then exit "$LOOKUP_EXIT"; fi\n'
        'printf "%s\\n" "$WORKFLOW_HISTORY" | jq -r "${@: -1}"\n'
    )
    gh.chmod(0o755)
    output = tmp_path / "output"
    output.touch()
    recovery = next(step for step in workflow["jobs"]["changes"]["steps"] if step.get("id") == "recovery")

    subprocess.run(
        ["bash", "-c", recovery["run"]],
        env={
            **os.environ,
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            "GITHUB_OUTPUT": str(output),
            "GITHUB_REPOSITORY": "computerlovetech/umbod",
            "GITHUB_RUN_NUMBER": "3",
            "BEFORE_SHA": "preceding-commit",
            "FORCED_PUSH": forced_push,
            "WORKFLOW_HISTORY": json.dumps({"workflow_runs": workflow_runs}),
            "LOOKUP_EXIT": str(lookup_exit),
        },
        check=True,
        timeout=10,
    )

    assert output.read_text() == expected_output


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


@pytest.mark.parametrize("component", ["backend", "lint", "semgrep"])
@pytest.mark.parametrize("selection", [None, "", "unknown"])
def test_completion_fails_closed_for_missing_or_invalid_selection(
    workflow: dict[str, Any], job_results: dict[str, Any], component: str, selection: str | None
) -> None:
    if selection is None:
        del job_results["changes"]["outputs"][component]
    else:
        job_results["changes"]["outputs"][component] = selection
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


@pytest.mark.parametrize("job", ["lint", "semgrep"])
def test_quality_jobs_use_locked_dependencies_and_python_314(
    workflow: dict[str, Any], job: str
) -> None:
    steps = workflow["jobs"][job]["steps"]
    assert steps[0]["uses"] == "useblacksmith/checkout@v1"
    setup = next(step for step in steps if step.get("uses") == "astral-sh/setup-uv@v7")
    assert setup["with"]["python-version"] == "3.14"
    assert setup["with"]["enable-cache"] == "true"
    assert not workflow["jobs"][job].get("continue-on-error")
    assert not any(step.get("continue-on-error") for step in steps)


def test_lint_checks_api_and_sdk_without_command_line_policy_overrides(workflow: dict[str, Any]) -> None:
    steps = workflow["jobs"]["lint"]["steps"]
    commands = [step for step in steps if "run" in step]
    assert {step["working-directory"] for step in commands} == {"umbod/api", "packages/umbod-sdk"}
    assert len(commands) == 2
    assert all(step["run"] == "uv run --locked ruff check ." for step in commands)
    setup = next(step for step in steps if step.get("uses") == "astral-sh/setup-uv@v7")
    assert set(setup["with"]["cache-dependency-glob"].splitlines()) == {"umbod/api/uv.lock", "packages/umbod-sdk/uv.lock"}


def test_semgrep_ci_runs_blocking_and_advisory_scans_without_targets(workflow: dict[str, Any]) -> None:
    job = workflow["jobs"]["semgrep"]
    assert job["defaults"]["run"]["working-directory"] == "umbod"
    setup = next(step for step in job["steps"] if step.get("uses") == "astral-sh/setup-uv@v7")
    assert setup["with"]["cache-dependency-glob"] == "umbod/uv.lock"
    commands = [shlex.split(step["run"]) for step in job["steps"] if "run" in step]
    assert commands == [
        ["bash", "scripts/run_semgrep.sh"],
        ["bash", "scripts/run_semgrep.sh", "--frontend-advisory"],
    ]


@pytest.mark.parametrize(
    ("mode", "configs", "blocking", "default_target"),
    [
        ([], {"../.semgrep.yml", "../.semgrep/production-design.yml", "../.semgrep/test-correctness.yml"}, True, "."),
        (["--frontend-advisory"], {"../.semgrep/frontend-advisory.yml"}, False, "frontend/src"),
    ],
)
@pytest.mark.parametrize("targets", [(), ("umbod/api", "umbod/folder with spaces")])
def test_semgrep_wrapper_uses_mode_specific_rules_and_preserves_requested_scope(
    tmp_path: Path,
    targets: tuple[str, ...],
    mode: list[str],
    configs: set[str],
    blocking: bool,
    default_target: str,
) -> None:
    uv = tmp_path / "uv"
    uv.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$PWD" "$@"\nexit 1\n')
    uv.chmod(0o755)
    arguments = [*mode, "--json", *targets] if targets else mode

    result = subprocess.run(
        ["bash", "umbod/scripts/run_semgrep.sh", *arguments],
        cwd=REPOSITORY,
        env={**os.environ, "CDPATH": ".", "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 1
    lines = result.stdout.splitlines()
    assert lines[:7] == [str(REPOSITORY / "umbod"), "run", "--locked", "--only-group", "dev", "semgrep", "scan"]
    expected_targets = [str(REPOSITORY / target) for target in targets] or [default_target]
    assert lines[-len(expected_targets):] == expected_targets
    options = lines[7:-len(expected_targets)]
    assert {value for option, value in zip(options, options[1:]) if option == "--config"} == configs
    assert {option for option in options if option.startswith("--") and option != "--config"} == {
        "--no-rewrite-rule-ids",
        "--metrics=off",
        *(["--error"] if blocking else []),
        *(["--json"] if targets else []),
    }


def test_frontend_sets_node_22_before_bun_and_dependency_installation(workflow: dict[str, Any]) -> None:
    steps = workflow["jobs"]["frontend"]["steps"]
    node_index = next(index for index, step in enumerate(steps) if step.get("uses") == "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1")
    bun_index = next(index for index, step in enumerate(steps) if step.get("uses") == "oven-sh/setup-bun@v2")
    install_index = next(index for index, step in enumerate(steps) if step.get("run") == "bun install --frozen-lockfile")
    assert steps[node_index]["with"]["node-version"] == "22"
    assert node_index < bun_index < install_index


def test_frontend_build_context_excludes_generated_coverage() -> None:
    ignored = (REPOSITORY / "umbod/frontend/.dockerignore").read_text().splitlines()
    assert "coverage" in ignored
