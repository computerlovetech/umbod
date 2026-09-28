import pytest
from scripts.release_versions import latest, resolve, select_shared_release


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


@pytest.mark.parametrize(
    ("sdk", "image", "sdk_checked", "image_checked", "increment", "expected"),
    [
        ("1.2.3b2", "1.2.3-beta.2", "0.1.0", "0.0.1", "beta", ("1.2.3b3", "1.2.3-beta.3")),
        ("1.2.3b2", "1.2.3", "0.1.0", "0.0.1", "patch", ("1.2.4", "1.2.4")),
        ("1.2.4", "1.2.3", "0.1.0", "0.0.1", "patch", ("1.2.5", "1.2.5")),
        ("", "0.1.2", "0.1.4", "0.0.1", "patch", ("0.1.5", "0.1.5")),
        ("1.3.0", "", "0.1.0", "1.2.0", "minor", ("1.4.0", "1.4.0")),
        ("", "", "0.1.0", "0.0.1-beta.4", "patch", ("0.1.0", "0.1.0")),
        ("", "", "0.1.0", "0.0.1-beta.4", "beta", ("0.1.0b1", "0.1.0-beta.1")),
    ],
)
def test_shared_release_uses_highest_history_or_bootstrap(
    sdk: str, image: str, sdk_checked: str, image_checked: str, increment: str, expected: tuple[str, str]
) -> None:
    selected = select_shared_release(sdk, image, sdk_checked, image_checked, increment)
    assert (selected.pep440(), selected.semver()) == expected


def test_stable_release_orders_above_same_triplet_beta() -> None:
    assert latest(["1.2.3-beta.9", "1.2.3", "latest", "1.2.2"]) == "1.2.3"


def test_shared_release_advances_published_version_when_other_side_is_absent() -> None:
    selected = select_shared_release("0.1.0", "", "0.1.0", "0.0.1", "patch")
    assert selected.pep440() == "0.1.1"


def test_release_version_rejects_unsupported_version() -> None:
    with pytest.raises(ValueError, match="Unsupported release version"):
        resolve("latest", "patch", False, False)
