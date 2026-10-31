import json
from pathlib import Path

import pytest

from scripts.release_versions import main


@pytest.mark.parametrize(
    ("tag", "sdk_version", "release_version"),
    [
        ("umbod-v1.2.3", "1.2.3", "1.2.3"),
        ("umbod-v0.0.0", "0.0.0", "0.0.0"),
        ("umbod-v1.2.3-beta.0", "1.2.3b0", "1.2.3-beta.0"),
        ("umbod-v1.2.3-beta.12", "1.2.3b12", "1.2.3-beta.12"),
    ],
)
def test_tag_cli_emits_synchronized_versions(
    tag: str, sdk_version: str, release_version: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--tag", tag]) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"sdk_version={sdk_version}",
        f"image_version={release_version}",
        f"chart_version={release_version}",
    ]


@pytest.mark.parametrize(
    "tag",
    [
        "",
        "1.2.3",
        "v1.2.3",
        "desktop-v1.2.3",
        "refs/tags/umbod-v1.2.3",
        "umbod-v01.2.3",
        "umbod-v1.02.3",
        "umbod-v1.2.03",
        "umbod-v1.2.3-beta.01",
        "umbod-v1.2",
        "umbod-v1.2.3.4",
        "umbod-v1x2x3",
        "umbod-v1.2.3b1",
        "umbod-v1.2.3-beta",
        "umbod-v1.2.3-beta.-1",
        "umbod-v1.2.3-alpha.1",
        "umbod-v1.2.3-rc.1",
        "umbod-v1.2.3+build",
        "umbod-v1.2.3-beta.1+build",
        "umbod-v1.2.3\n",
        " umbod-v1.2.3",
        "umbod-v1.2.3 ",
        "umbod-v１.2.3",
    ],
)
def test_tag_cli_rejects_noncanonical_tags_without_outputs(tag: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--tag", tag])
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Unsupported release tag" in captured.err


@pytest.mark.parametrize("arguments", [[], ["--current", "1.2.3"], ["--latest"], ["--shared"]])
def test_tag_cli_requires_tag_and_rejects_obsolete_modes(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == 2



@pytest.mark.parametrize(
    "tag,semver,sdk_version",
    [
        ("umbod-v1.2.3", "1.2.3", "1.2.3"),
        ("umbod-v1.2.3-beta.4", "1.2.3-beta.4", "1.2.3b4"),
    ],
)
def test_matching_committed_metadata_emits_versions_without_modifying_file(
    tag: str,
    semver: str,
    sdk_version: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    metadata = tmp_path / "release-metadata.json"
    committed = json.dumps({"chartVersion": semver, "imageTag": semver, "sdkVersion": sdk_version})
    metadata.write_text(committed)
    assert main(["--tag", tag, "--metadata", str(metadata)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"sdk_version={sdk_version}",
        f"image_version={semver}",
        f"chart_version={semver}",
    ]
    assert metadata.read_text() == committed


@pytest.mark.parametrize(
    "content",
    [
        '{"chartVersion":"1.2.2","imageTag":"1.2.3","sdkVersion":"1.2.3"}',
        '{"chartVersion":"1.2.3","imageTag":"1.2.2","sdkVersion":"1.2.3"}',
        '{"chartVersion":"1.2.3","imageTag":"1.2.3","sdkVersion":"1.2.2"}',
        '{"chartVersion":"1.2.3","imageTag":"1.2.3"}',
        '{"chartVersion":"1.2.3","imageTag":"1.2.3","sdkVersion":"1.2.3","extra":"value"}',
        '[]',
        'null',
        '{broken',
    ],
)
def test_invalid_committed_metadata_fails_before_emitting_version_outputs(
    content: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    metadata = tmp_path / "release-metadata.json"
    metadata.write_text(content)
    with pytest.raises(SystemExit) as error:
        main(["--tag", "umbod-v1.2.3", "--metadata", str(metadata)])
    assert error.value.code == 2
    assert capsys.readouterr().out == ""
    assert metadata.read_text() == content


def test_missing_committed_metadata_fails_before_emitting_outputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--tag", "umbod-v1.2.3", "--metadata", str(tmp_path / "missing.json")])
    assert error.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "Cannot read release metadata" in output.err
