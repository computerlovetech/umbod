import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml


@pytest.fixture
def repository() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture
def release_workflow(repository: Path) -> dict[str, Any]:
    return yaml.load(
        (repository / ".github/workflows/umbod-release.yml").read_text(), Loader=yaml.BaseLoader
    )


def test_production_and_preview_deploy_to_separate_workers_and_domains(repository: Path) -> None:
    config = json.loads((repository / "website/wrangler.jsonc").read_text())
    preview = config["env"]["preview"]
    assert config["name"] == "umbod-website"
    assert config["routes"] == [{"pattern": "umbod.ai", "custom_domain": True}]
    assert preview["name"] == "umbod-website-preview"
    assert preview["routes"] == [{"pattern": "preview.umbod.ai", "custom_domain": True}]
    assert preview["assets"] == config["assets"]


def test_website_ci_validates_without_deploying_or_requiring_cloudflare_secrets(repository: Path) -> None:
    workflow: dict[str, Any] = yaml.load(
        (repository / ".github/workflows/website-ci.yml").read_text(), Loader=yaml.BaseLoader
    )
    assert set(workflow["jobs"]) == {"harness-linting", "website"}
    assert "CLOUDFLARE_API_TOKEN" not in str(workflow)
    assert "wrangler deploy" not in str(workflow)
    assert workflow["jobs"]["website"]["steps"][-1]["run"] == "bun run build"


def test_production_promotion_waits_for_successful_release_artifacts(release_workflow: dict[str, Any]) -> None:
    assert release_workflow["on"] == {"push": {"tags": ["umbod-v*"]}}
    website = release_workflow["jobs"]["website"]
    assert website["needs"] == ["plan", "chart"]
    assert "if" not in website
    assert "continue-on-error" not in str(website)
    assert website["concurrency"] == {"group": "website-production", "cancel-in-progress": "false"}


def test_production_builds_verified_release_before_advancing_branch(release_workflow: dict[str, Any]) -> None:
    website = release_workflow["jobs"]["website"]
    assert website["permissions"] == {"contents": "write"}
    assert website["steps"][0]["with"] == {
        "ref": "${{ needs.plan.outputs.release_sha }}",
        "fetch-depth": "0",
        "persist-credentials": "true",
    }
    commands = [step["run"] for step in website["steps"] if step.get("working-directory") == "website"]
    assert commands == [
        "bun install --frozen-lockfile",
        "bun run build:release",
        "bun run test",
    ]
    promotion = website["steps"][-1]
    assert promotion["env"] == {"RELEASE_SHA": "${{ needs.plan.outputs.release_sha }}"}
    assert promotion["run"] == 'git push origin "${RELEASE_SHA}:refs/heads/production"'
    assert "--force" not in promotion["run"]
    assert "CLOUDFLARE_" not in str(release_workflow)
    assert "wrangler deploy" not in str(release_workflow)


def test_release_build_validates_metadata_before_build_without_changing_preview_build(repository: Path) -> None:
    scripts = json.loads((repository / "website/package.json").read_text())["scripts"]
    assert scripts["build:release"] == "bash scripts/prepare-release.sh && bun run build"
    assert scripts["build"] == "bun run docs && vite build"


def run_git(directory: Path, arguments: list[str]) -> str:
    return subprocess.run(
        ["git", "-C", str(directory), *arguments],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def release_checkout(repository: Path, tmp_path: Path) -> Path:
    remote = tmp_path / "origin"
    remote.mkdir()
    run_git(remote, ["init", "--bare"])
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    run_git(checkout, ["init", "--initial-branch=main"])
    run_git(checkout, ["config", "user.email", "release-test@umbod.ai"])
    run_git(checkout, ["config", "user.name", "Release test"])
    for relative in ["website/scripts/prepare-release.sh", "umbod/scripts/release_versions.py"]:
        destination = checkout / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((repository / relative).read_text())
    (checkout / "release-metadata.json").write_text(json.dumps({
        "chartVersion": "0.0.1",
        "imageTag": "0.0.1",
        "sdkVersion": "0.0.1",
    }))
    run_git(checkout, ["add", "."])
    run_git(checkout, ["commit", "-m", "Release source"])
    run_git(checkout, ["remote", "add", "origin", str(remote)])
    run_git(checkout, ["push", "origin", "main"])
    return checkout


@pytest.mark.parametrize(
    "tag,semver,sdk_version",
    [
        ("umbod-v1.2.3", "1.2.3", "1.2.3"),
        ("umbod-v1.2.3-beta.4", "1.2.3-beta.4", "1.2.3b4"),
    ],
)
def test_release_build_fetches_exact_tag_and_preserves_matching_committed_versions(
    release_checkout: Path, tag: str, semver: str, sdk_version: str
) -> None:
    metadata_path = release_checkout / "release-metadata.json"
    committed = json.dumps({"chartVersion": semver, "imageTag": semver, "sdkVersion": sdk_version})
    metadata_path.write_text(committed)
    run_git(release_checkout, ["add", "release-metadata.json"])
    run_git(release_checkout, ["commit", "-m", "Align release metadata"])
    run_git(release_checkout, ["tag", tag])
    run_git(release_checkout, ["push", "origin", tag])
    run_git(release_checkout, ["tag", "-d", tag])
    result = subprocess.run(
        ["bash", "scripts/prepare-release.sh"],
        cwd=release_checkout / "website",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert metadata_path.read_text() == committed
    assert json.loads(metadata_path.read_text()) == {
        "chartVersion": semver,
        "imageTag": semver,
        "sdkVersion": sdk_version,
    }


@pytest.mark.parametrize("tags", [[], ["umbod-v01.2.3"], ["umbod-v1.2.3", "umbod-v1.2.4"]])
def test_release_build_rejects_missing_invalid_or_ambiguous_tags(
    release_checkout: Path, tags: list[str]
) -> None:
    for tag in tags:
        run_git(release_checkout, ["tag", tag])
        run_git(release_checkout, ["push", "origin", tag])
    original = (release_checkout / "release-metadata.json").read_text()
    result = subprocess.run(
        ["bash", "scripts/prepare-release.sh"],
        cwd=release_checkout / "website",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert (release_checkout / "release-metadata.json").read_text() == original


@pytest.mark.parametrize(
    "production_reference,release_reference,expected_status",
    [("missing", "newer", 0), ("older", "newer", 0), ("newer", "older", 1)],
)
def test_promotion_creates_or_advances_exact_release_branch_without_rollback(
    release_workflow: dict[str, Any],
    release_checkout: Path,
    production_reference: str,
    release_reference: str,
    expected_status: int,
) -> None:
    older = run_git(release_checkout, ["rev-parse", "HEAD"])
    (release_checkout / "release.txt").write_text("Next release")
    run_git(release_checkout, ["add", "release.txt"])
    run_git(release_checkout, ["commit", "-m", "Next release"])
    newer = run_git(release_checkout, ["rev-parse", "HEAD"])
    revisions = {"older": older, "newer": newer}
    if production_reference != "missing":
        run_git(release_checkout, ["push", "origin", f"{revisions[production_reference]}:refs/heads/production"])
    selected = revisions[release_reference]
    promotion = release_workflow["jobs"]["website"]["steps"][-1]
    result = subprocess.run(
        ["bash", "-c", promotion["run"]],
        cwd=release_checkout,
        env={**os.environ, "RELEASE_SHA": selected},
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) == (expected_status == 0), result.stderr
    actual = run_git(release_checkout, ["ls-remote", "origin", "refs/heads/production"]).split()[0]
    assert actual == (selected if expected_status == 0 else newer)


def test_release_build_rejects_local_tag_deleted_from_origin(release_checkout: Path) -> None:
    tag = "umbod-v1.2.3"
    run_git(release_checkout, ["tag", tag])
    run_git(release_checkout, ["push", "origin", tag])
    run_git(release_checkout, ["push", "origin", f":refs/tags/{tag}"])
    original = (release_checkout / "release-metadata.json").read_text()
    result = subprocess.run(
        ["bash", "scripts/prepare-release.sh"],
        cwd=release_checkout / "website",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert (release_checkout / "release-metadata.json").read_text() == original
    assert run_git(release_checkout, ["tag", "--list", tag]) == ""


@pytest.mark.parametrize("change_released_content", [False, True])
def test_production_bootstrap_only_accepts_deployment_changes_above_release(
    release_checkout: Path, change_released_content: bool
) -> None:
    tag = "umbod-v1.2.3-beta.4"
    run_git(release_checkout, ["tag", tag])
    run_git(release_checkout, ["push", "origin", tag])
    (release_checkout / "website/release-source.tag").write_text(f"{tag}\n")
    if change_released_content:
        (release_checkout / "website/index.html").write_text("Unreleased content")
    run_git(release_checkout, ["add", "."])
    run_git(release_checkout, ["commit", "-m", "Bootstrap deployment"])
    original = (release_checkout / "release-metadata.json").read_text()
    result = subprocess.run(
        ["bash", "scripts/prepare-release.sh"],
        cwd=release_checkout / "website",
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) != change_released_content, result.stderr
    if change_released_content:
        assert (release_checkout / "release-metadata.json").read_text() == original
    else:
        assert json.loads((release_checkout / "release-metadata.json").read_text()) == {
            "chartVersion": "1.2.3-beta.4",
            "imageTag": "1.2.3-beta.4",
            "sdkVersion": "1.2.3b4",
        }


def test_production_bootstrap_rejects_more_than_one_commit_above_release(release_checkout: Path) -> None:
    tag = "umbod-v1.2.3"
    run_git(release_checkout, ["tag", tag])
    run_git(release_checkout, ["push", "origin", tag])
    (release_checkout / "website/release-source.tag").write_text(f"{tag}\n")
    run_git(release_checkout, ["add", "."])
    run_git(release_checkout, ["commit", "-m", "Bootstrap deployment"])
    run_git(release_checkout, ["commit", "--allow-empty", "-m", "Unreleased follow-up"])
    result = subprocess.run(
        ["bash", "scripts/prepare-release.sh"],
        cwd=release_checkout / "website",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "directly follow its release commit" in result.stderr


def test_production_bootstrap_builds_from_shallow_cloudflare_checkout(release_checkout: Path) -> None:
    tag = "umbod-v1.2.3"
    run_git(release_checkout, ["tag", tag])
    run_git(release_checkout, ["push", "origin", tag])
    (release_checkout / "website/release-source.tag").write_text(f"{tag}\n")
    run_git(release_checkout, ["add", "."])
    run_git(release_checkout, ["commit", "-m", "Bootstrap deployment"])
    run_git(release_checkout, ["push", "origin", "HEAD:refs/heads/production"])
    remote = Path(run_git(release_checkout, ["remote", "get-url", "origin"]))
    shallow = release_checkout.parent / "shallow-bootstrap"
    subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", "production", remote.as_uri(), str(shallow)],
        capture_output=True,
        text=True,
        check=True,
    )
    result = subprocess.run(
        ["bash", "scripts/prepare-release.sh"],
        cwd=shallow / "website",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert run_git(shallow, ["rev-parse", "--is-shallow-repository"]) == "true"
    assert json.loads((shallow / "release-metadata.json").read_text())["chartVersion"] == "1.2.3"



@pytest.mark.parametrize("tag", ["umbod-v1.2.3", "umbod-v1.2.3-beta.4"])
def test_ordinary_release_build_rejects_version_drift_without_rewriting_metadata(
    release_checkout: Path, tag: str
) -> None:
    run_git(release_checkout, ["tag", tag])
    run_git(release_checkout, ["push", "origin", tag])
    metadata = release_checkout / "release-metadata.json"
    committed = metadata.read_text()
    result = subprocess.run(
        ["bash", "scripts/prepare-release.sh"],
        cwd=release_checkout / "website",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Update committed release metadata before tagging" in result.stderr
    assert metadata.read_text() == committed



def test_release_promotion_is_only_workflow_job_with_repository_contents_write(repository: Path) -> None:
    writers: list[tuple[str, str]] = []
    for path in (repository / ".github/workflows").glob("*.yml"):
        workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
        permissions = workflow.get("permissions", {})
        assert permissions != "write-all", path.name
        if isinstance(permissions, dict):
            assert permissions.get("contents") != "write", path.name
        for name, job in workflow.get("jobs", {}).items():
            permissions = job.get("permissions", {})
            assert permissions != "write-all", (path.name, name)
            if isinstance(permissions, dict) and permissions.get("contents") == "write":
                writers.append((path.name, name))
    assert writers == [("umbod-release.yml", "website")]
