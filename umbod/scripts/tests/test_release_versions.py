import pytest

from scripts.release_versions import resolve


@pytest.mark.parametrize(
    ("current", "increment", "bootstrap", "pep440", "expected"),
    [
        ("0.0.1-beta.2", "beta", False, False, "0.0.1-beta.3"),
        ("0.0.1-beta.2", "patch", False, False, "0.0.1"),
        ("1.4.2", "beta", False, False, "1.4.3-beta.1"),
        ("1.4.2", "minor", False, False, "1.5.0"),
        ("1.4.2", "major", False, False, "2.0.0"),
        ("0.0.1-beta.2", "beta", True, False, "0.0.1-beta.2"),
        ("0.0.1-beta.2", "patch", True, False, "0.0.1"),
        ("0.1.0", "patch", True, True, "0.1.0"),
        ("0.1.0", "beta", True, True, "0.1.0b1"),
        ("0.1.0b3", "patch", False, True, "0.1.0"),
    ],
)
def test_release_version_resolves_selected_increment(
    current: str, increment: str, bootstrap: bool, pep440: bool, expected: str
) -> None:
    assert resolve(current, increment, bootstrap, pep440) == expected


def test_release_version_rejects_unsupported_version() -> None:
    with pytest.raises(ValueError, match="Unsupported release version"):
        resolve("latest", "patch", False, False)
