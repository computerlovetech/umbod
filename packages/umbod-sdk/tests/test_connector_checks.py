import re

import pytest

from umbod_sdk.connector_checks import (
    ConnectorMetadataChecker,
    EntryPointMetadataChecker,
    InMemoryMetadataReader,
    MetadataCheckError,
    MetadataContent,
    MetadataReader,
    MetadataRequest,
)


def _check(text: str) -> tuple[str, ...]:
    reader: MetadataReader = InMemoryMetadataReader(MetadataContent(text=text))
    checker: ConnectorMetadataChecker = EntryPointMetadataChecker(reader)
    return checker.check(MetadataRequest(project_directory=".")).entry_names


def test_check_accepts_multiple_dotted_targets_without_loading_modules() -> None:
    entries = _check(
        '[project.entry-points."umbod.connectors"]\n'
        'first-plugin = "missing.module:Plugin.instance"\n'
        'other_plugin = "another.nested.module:Export"\n'
    )
    assert entries == ("first-plugin", "other_plugin")


@pytest.mark.parametrize(
    "target",
    ["pkg : Plugin", " pkg:Plugin ", "pkg.module : Plugin.instance", "pkg: Plugin"],
)
def test_check_accepts_whitespace_around_entry_point_separator(target: str) -> None:
    entries = _check(
        '[project.entry-points."umbod.connectors"]\n'
        f'plugin = "{target}"\n'
    )
    assert entries == ("plugin",)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", "[project]"),
        ("[project]\n", "[project.entry-points]"),
        ('[project.entry-points]\n', '[project.entry-points."umbod.connectors"]'),
        ('[project.entry-points."umbod.connectors"]\n', "at least one entry"),
        ('[project.entry-points]\n"umbod.connectors" = "wrong"\n', "malformed"),
        ('[project.entry-points."umbod.connectors"]\n"bad name" = "pkg:Plugin"\n', "invalid entry name"),
        ('[project.entry-points."umbod.connectors"]\nvalid = 7\n', "entry 'valid'"),
        ('[project.entry-points."umbod.connectors"]\nvalid = ["pkg:Plugin"]\n', "entry 'valid'"),
        ('[project.entry-points."umbod.connectors"]\nvalid = "pkg"\n', "entry 'valid'"),
        ('[project.entry-points."umbod.connectors"]\nvalid = ":Plugin"\n', "entry 'valid'"),
        ('[project.entry-points."umbod.connectors"]\nvalid = "pkg:"\n', "entry 'valid'"),
        ('[project.entry-points."umbod.connectors"]\nvalid = "pkg:bad-name"\n', "entry 'valid'"),
        ('[project.entry-points."umbod.connectors"]\nvalid = "pkg:Plugin extra"\n', "entry 'valid'"),
        ("[project\n", "malformed TOML"),
    ],
)
def test_check_rejects_invalid_metadata(text: str, expected: str) -> None:
    with pytest.raises(MetadataCheckError, match=re.escape(expected)):
        _check(text)
