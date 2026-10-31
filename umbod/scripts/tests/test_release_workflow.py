from pathlib import Path

import pytest


@pytest.fixture
def workflow() -> str:
    return (Path(__file__).resolve().parents[3] / ".github/workflows/umbod-release.yml").read_text()


def test_release_workflow_only_accepts_umbod_tag_pushes(workflow: str) -> None:
    trigger = workflow.split("on:\n", 1)[1].split("\nconcurrency:", 1)[0]
    assert trigger == "  push:\n    tags:\n      - 'umbod-v*'\n"
    assert "inputs." not in workflow
    assert "group: umbod-release-${{ github.ref }}\n  cancel-in-progress: false" in workflow


def test_release_workflow_derives_all_versions_from_full_tag(workflow: str) -> None:
    assert 'python3 umbod/scripts/release_versions.py --tag "${GITHUB_REF_NAME}" --metadata release-metadata.json >> "${GITHUB_OUTPUT}"' in workflow
    for version in ("sdk_version", "image_version", "chart_version"):
        assert f"{version}: ${{{{ steps.resolve.outputs.{version} }}}}" in workflow
    for obsolete in ("--latest", "--shared", "--increment", "--bootstrap", "highest_common", "chart_image_version"):
        assert obsolete not in workflow


def test_release_workflow_verifies_tag_commit_on_main_with_exact_successful_push_ci(workflow: str) -> None:
    plan = workflow.split("\n  sdk-publish:", 1)[0]
    assert "fetch-depth: 0" in plan
    assert '"${GITHUB_EVENT_NAME}" == "push"' in plan
    assert '"${GITHUB_REF}" == refs/tags/umbod-v*' in plan
    assert 'release_sha="$(git rev-parse HEAD^{commit})"' in plan
    assert "git fetch origin main:refs/remotes/origin/main" in plan
    assert 'git merge-base --is-ancestor "${release_sha}" refs/remotes/origin/main' in plan
    assert "actions/workflows/umbod-ci.yml/runs?head_sha=${release_sha}&branch=main&status=success" in plan
    assert '.head_sha ==' in plan
    assert '.head_branch == "main" and .event == "push" and .conclusion == "success"' in plan
    assert '[[ "${count}" -gt 0 ]]' in plan
    assert plan.index('echo "release_sha=${release_sha}"') > plan.index('[[ "${count}" -gt 0 ]]')
    assert "release_sha: ${{ steps.provenance.outputs.release_sha }}" in plan


def test_release_workflow_uses_verified_commit_for_all_publication_sources(workflow: str) -> None:
    publication = workflow.split("\n  sdk-publish:", 1)[1]
    assert publication.count("uses: actions/checkout@v6") == 4
    assert publication.count("ref: ${{ needs.plan.outputs.release_sha }}") == 4
    assert "org.opencontainers.image.revision=${{ needs.plan.outputs.release_sha }}" in publication
    assert "github.sha" not in workflow


def test_release_workflow_requires_sdk_then_all_images_then_chart(workflow: str) -> None:
    sdk = workflow.split("\n  sdk-publish:", 1)[1].split("\n  images:", 1)[0]
    images = workflow.split("\n  images:", 1)[1].split("\n  chart:", 1)[0]
    chart = workflow.split("\n  chart:", 1)[1].split("\n  website:", 1)[0]
    assert "needs: plan" in sdk
    assert "needs: [plan, sdk-publish]" in images
    assert "needs: [plan, images]" in chart
    for job in (sdk, images, chart):
        assert "\n    if:" not in job
        assert "continue-on-error" not in job
    assert images.count("- {name:") == 3
    for name in ("connector-builder", "core", "frontend"):
        assert f"- {{name: {name}," in images


def test_release_workflow_checks_exact_registry_collisions_and_fails_lookup_errors(workflow: str) -> None:
    plan = workflow.split("\n  sdk-publish:", 1)[0]
    assert "for package in umbod umbod-frontend umbod-connector-builder; do" in plan
    assert 'tags="$(package_tags "${package}")"' in plan
    assert 'grep -Fxq "${IMAGE_VERSION}" <<< "${tags}"' in plan
    assert 'chart_tags="$(package_tags \'charts/umbod\')"' in plan
    assert 'grep -Fxq "${CHART_VERSION}" <<< "${chart_tags}"' in plan
    assert "per_page=100&page=${page}" in plan
    assert '[[ "${count}" -lt 100 ]] && break' in plan
    assert "page=$((page + 1))" in plan
    assert 'if [[ "${status}" == "404" && "${page}" == 1 ]]' in plan
    assert '[[ "${status}" == "200" ]] ||' in plan
    assert "GHCR lookup failed" in plan
    assert "return 1;" in plan
    assert "pypi/umbod/${SDK_VERSION}/json" in plan
    assert '[[ "${sdk_status}" == "404" ]] ||' in plan
    assert "PyPI preflight failed" in plan
    assert "helm show" not in plan


def test_release_workflow_preserves_sdk_stamping_and_multiarch_images(workflow: str) -> None:
    assert 'uv version --no-sync "${VERSION}"' in workflow
    assert "uv build --no-sources" in workflow
    assert ".dist-info/METADATA" in workflow
    assert "/PKG-INFO" in workflow
    assert "-m scripts.stamp_sdk_version packages/umbod-sdk/pyproject.toml umbod/api/uv.lock" in workflow
    assert 'actual="$(docker run --rm --entrypoint python' in workflow
    assert '[[ "${actual}" == "${SDK_VERSION}" ]]' in workflow
    assert "platforms: linux/amd64,linux/arm64" in workflow
    assert "tags: ${{ matrix.image }}:${{ needs.plan.outputs.image_version }}" in workflow
    assert "org.opencontainers.image.umbod.sdk.version=${{ needs.plan.outputs.sdk_version }}" in workflow
    assert 'format(\'UMBOD_RELEASE={0}\', needs.plan.outputs.image_version)' in workflow


def test_release_workflow_stamps_and_validates_chart_with_same_image_version(workflow: str) -> None:
    chart = workflow.split("\n  chart:", 1)[1].split("\n  website:", 1)[0]
    assert chart.count("IMAGE_VERSION: ${{ needs.plan.outputs.image_version }}") == 2
    assert "VERSION: ${{ needs.plan.outputs.chart_version }}" in chart
    assert 'f"version: {version}"' in chart
    assert 'appVersion: "{image_version}"' in chart
    assert "repository: ghcr.io/computerlovetech/umbod" in chart
    assert "repository: ghcr.io/computerlovetech/umbod-frontend" in chart
    assert '"${RUNNER_TEMP}/umbod/scripts/validate.sh"' in chart
    assert chart.index("scripts/validate.sh") < chart.index("helm package") < chart.index("helm push")
    assert 'shown="$(helm show chart' in chart



def test_release_metadata_validation_precedes_artifact_publication(workflow: str) -> None:
    plan = workflow.split("\n  sdk-publish:", 1)[0]
    validation = 'python3 umbod/scripts/release_versions.py --tag "${GITHUB_REF_NAME}" --metadata release-metadata.json'
    assert plan.index(validation) < plan.index("Ensure release versions are unpublished")
    assert workflow.index(validation) < workflow.index("Build and publish SDK")
