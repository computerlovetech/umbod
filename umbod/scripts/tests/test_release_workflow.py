from pathlib import Path


def test_release_workflow_couples_sdk_and_image_publication() -> None:
    workflow = (Path(__file__).resolve().parents[3] / ".github/workflows/umbod-release.yml").read_text()
    assert "      release:\n" in workflow
    assert "      release_increment:\n" in workflow
    assert "      sdk:\n" not in workflow
    assert "      images:\n" not in workflow
    assert "      sdk_increment:\n" not in workflow
    assert "      images_increment:\n" not in workflow
    assert "needs.sdk-publish.result == 'success'" in workflow
    assert "needs.sdk-publish.result == 'skipped'" not in workflow
    assert "--shared --sdk-current" in workflow
    assert 'grep -Fxq "${image_version}" <<< "${tags}"' in workflow
    assert 'pypi/umbod/${SDK_VERSION}/json' in workflow
    assert "-m scripts.stamp_sdk_version packages/umbod-sdk/pyproject.toml umbod/api/uv.lock" in workflow
    assert "actual=\"$(docker run --rm --entrypoint python" in workflow
