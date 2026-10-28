import json
import subprocess
from pathlib import Path
from typing import NamedTuple, TypedDict, cast

import pytest


PATCH_RULE = "python.tests.review-patching"
PRIVATE_RULE = "python.tests.review-private-monkeypatch"


class ScanCase(NamedTuple):
    name: str
    path: str
    source: str
    expected_rules: tuple[str, ...]


class FindingExtra(TypedDict):
    severity: str
    message: str


class Finding(TypedDict):
    check_id: str
    path: str
    extra: FindingExtra


class ScanPaths(TypedDict):
    scanned: list[str]


class ScanOutput(TypedDict):
    results: list[Finding]
    errors: list[dict[str, object]]
    paths: ScanPaths


PATCH_IMPORTS = (
    ("canonical", "import unittest.mock", "unittest.mock.patch"),
    ("from_unittest", "from unittest import mock", "mock.patch"),
    ("direct", "from unittest.mock import patch", "patch"),
    ("patch_alias", "from unittest.mock import patch as replacement", "replacement"),
    ("module_alias", "import unittest.mock as mocking", "mocking.patch"),
    ("from_alias", "from unittest import mock as mocking", "mocking.patch"),
    ("legacy", "import mock", "mock.patch"),
    ("legacy_alias", "import mock as mocking", "mocking.patch"),
    ("legacy_direct", "from mock import patch as replacement", "replacement"),
)
PATCH_OPERATIONS = (
    ("call", '("package.service.operation")'),
    ("object", '.object(service, "operation")'),
    ("dict", '.dict(environment, {"KEY": "value"})'),
    ("multiple", '.multiple(service, operation=replacement_value)'),
)
PATCH_CONTEXTS = (
    ("expression", "{operation}\n"),
    ("stored", "patcher = {operation}\npatcher.start()\npatcher.stop()\n"),
    ("decorator", "@{operation}\ndef test_behavior(replacement):\n    assert replacement\n"),
    ("context", "with {operation} as patched_value:\n    assert patched_value\n"),
)
PATCH_CASES = tuple(
    ScanCase(
        f"{import_name}_{operation_name}_{context_name}",
        f"tests/test_{import_name}_{operation_name}_{context_name}.py",
        f"{import_source}\n{context.format(operation=patch_name + operation)}",
        (PATCH_RULE,),
    )
    for import_name, import_source, patch_name in PATCH_IMPORTS
    for operation_name, operation in PATCH_OPERATIONS
    for context_name, context in PATCH_CONTEXTS
)
FIXTURE_CASES = tuple(
    ScanCase(
        f"{fixture_name}_{operation_name}",
        f"tests/test_{fixture_name}_{operation_name}.py",
        f"def test_behavior({fixture_name}):\n    {fixture_name}.patch{operation}\n",
        (PATCH_RULE,),
    )
    for fixture_name in (
        "mocker", "session_mocker", "module_mocker", "class_mocker", "package_mocker"
    )
    for operation_name, operation in PATCH_OPERATIONS
)
PRIVATE_OPERATIONS = (
    ('setattr_object', 'monkeypatch.setattr(service, "_operation", replacement)'),
    ('setattr_object_optional', 'monkeypatch.setattr(service, "_operation", replacement, raising=False)'),
    ('delattr_object', 'monkeypatch.delattr(service, "_operation")'),
    ('delattr_object_optional', 'monkeypatch.delattr(service, "_operation", raising=False)'),
    ('setattr_dotted', 'monkeypatch.setattr("package.service._operation", replacement)'),
    ('setattr_dotted_optional', 'monkeypatch.setattr("package.service._operation", replacement, raising=False)'),
    ('delattr_dotted', 'monkeypatch.delattr("package.service._operation")'),
    ('delattr_dotted_optional', 'monkeypatch.delattr("package.service._operation", raising=False)'),
    ('single_quotes', "monkeypatch.setattr(service, '_operation', replacement)"),
    ('single_quotes_dotted', "monkeypatch.delattr('package.service._operation')"),
)
PRIVATE_CASES = tuple(
    ScanCase(name, f"tests/test_{name}.py", f"def test_behavior(monkeypatch):\n    {operation}\n", (PRIVATE_RULE,))
    for name, operation in PRIVATE_OPERATIONS
)
NEGATIVE_OPERATIONS = (
    ('unused_patch', 'from unittest.mock import patch'),
    ('unused_patch_alias', 'from unittest.mock import patch as replacement'),
    ('unused_legacy_patch', 'from mock import patch'),
    ('mock_construction', 'from unittest.mock import Mock\nreplacement = Mock()'),
    ('async_mock_construction', 'from unittest.mock import AsyncMock\nreplacement = AsyncMock()'),
    ('magic_mock_construction', 'from unittest.mock import MagicMock\nreplacement = MagicMock()'),
    ('autospec_construction', 'from unittest.mock import create_autospec\nreplacement = create_autospec(service)'),
    ('sentinel', 'from unittest.mock import sentinel\nreplacement = sentinel.value'),
    ('legacy_mock', 'from mock import Mock, AsyncMock, MagicMock\nreplacement = Mock()'),
    ('owned_fake_state', 'class FakeService:\n    def __init__(self) -> None:\n        self._events = []\n\nfake = FakeService()\nfake._events.append("event")\nassert fake._events'),
    ('private_access', 'assert service._operation()'),
    ('private_assignment', 'service._operation = replacement'),
    ('public_setattr', 'monkeypatch.setattr(service, "operation", replacement)'),
    ('public_delattr', 'monkeypatch.delattr(service, "operation")'),
    ('public_dotted_setattr', 'monkeypatch.setattr("package.service.operation", replacement)'),
    ('public_dotted_delattr', 'monkeypatch.delattr("package.service.operation")'),
    ('dunder_setattr', 'monkeypatch.setattr(service, "__call__", replacement)'),
    ('dunder_delattr', 'monkeypatch.delattr(service, "__call__")'),
    ('dunder_dotted_setattr', 'monkeypatch.setattr("package.service.__call__", replacement)'),
    ('dunder_dotted_delattr', 'monkeypatch.delattr("package.service.__call__")'),
    ('private_module_public_attribute', 'monkeypatch.setattr("package._service.operation", replacement)'),
    ('environment_set', 'monkeypatch.setenv("_KEY", "value")'),
    ('environment_delete', 'monkeypatch.delenv("_KEY")'),
    ('item_set', 'monkeypatch.setitem(environment, "_KEY", "value")'),
    ('item_delete', 'monkeypatch.delitem(environment, "_KEY")'),
    ('unrelated_setattr', 'service.setattr(service, "_operation", replacement)'),
    ('unrelated_delattr', 'service.delattr(service, "_operation")'),
    ('unrelated_patch', 'service.patch("package.service.operation")'),
    ('unrelated_patch_object', 'service.patch.object(service, "operation")'),
    ('public_module_patch', 'from package.public_api import patch\npatch("resource")'),
    ('private_module_patch', 'from package._internal import patch\npatch("resource")'),
    ('unrelated_imported_mock', 'from package import mock\nmock.patch("resource")'),
)
NEGATIVE_CASES = tuple(
    ScanCase(name, f"tests/test_{name}.py", f"{source}\n", ())
    for name, source in NEGATIVE_OPERATIONS
)
SCOPE_CASES = tuple(
    ScanCase(
        f"scope_{name}",
        path,
        'import unittest.mock\nunittest.mock.patch("package.service.operation")\n'
        'monkeypatch.setattr(service, "_operation", replacement)\n',
        expected_rules,
    )
    for name, path, expected_rules in (
        ("test_tree", "tests/helpers.py", (PATCH_RULE, PRIVATE_RULE)),
        ("nested_test_tree", "package/tests/helpers.py", (PATCH_RULE, PRIVATE_RULE)),
        ("live_runtime", "live_runtime_tests/helpers.py", (PATCH_RULE, PRIVATE_RULE)),
        ("nested_live_runtime", "package/live_runtime_tests/helpers.py", (PATCH_RULE, PRIVATE_RULE)),
        ("prefix", "package/test_service.py", (PATCH_RULE, PRIVATE_RULE)),
        ("suffix", "package/service_test.py", (PATCH_RULE, PRIVATE_RULE)),
        ("conftest", "package/conftest.py", (PATCH_RULE, PRIVATE_RULE)),
        ("production", "src/service.py", ()),
        ("similar_tree", "test_helpers/service.py", ()),
    )
)
CASES = PATCH_CASES + FIXTURE_CASES + PRIVATE_CASES + NEGATIVE_CASES + SCOPE_CASES


@pytest.fixture(scope="module")
def findings_by_case(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[Finding]]:
    repository_root = Path(__file__).resolve().parents[3]
    fixture_root = tmp_path_factory.mktemp("semgrep_test_practices")
    (fixture_root / ".semgrepignore").write_text(
        (repository_root / ".semgrepignore").read_text(encoding="utf-8"), encoding="utf-8"
    )
    for case in CASES:
        source_path = fixture_root / case.path
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(case.source, encoding="utf-8")
    result = subprocess.run(
        [
            "uv", "run", "--project", str(repository_root / "umbod"), "--locked",
            "semgrep", "scan", "--config", str(repository_root / ".semgrep.yml"),
            "--json", "--metrics=off", "--disable-version-check",
            "--jobs=1", "--project-root", str(fixture_root), str(fixture_root),
        ],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=True,
        timeout=180,
    )
    scan = cast(ScanOutput, json.loads(result.stdout))
    assert not scan["errors"], scan["errors"]
    scanned_paths = {
        Path(path).relative_to(fixture_root).as_posix() for path in scan["paths"]["scanned"]
    }
    assert scanned_paths == {case.path for case in CASES}
    findings: dict[str, list[Finding]] = {case.path: [] for case in CASES}
    for finding in scan["results"]:
        relative_path = Path(finding["path"]).relative_to(fixture_root).as_posix()
        findings[relative_path].append(finding)
    return findings


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_shared_rules_report_only_contextual_test_practice_warnings(
    case: ScanCase, findings_by_case: dict[str, list[Finding]]
) -> None:
    findings = findings_by_case[case.path]
    assert sorted(finding["check_id"] for finding in findings) == sorted(case.expected_rules)
    for finding in findings:
        assert finding["extra"]["severity"] == "WARNING"
        message = finding["extra"]["message"]
        for phrase in (
            "needed in this context?", "implementation details", "bypass real behavior",
            "dependency-injection seam", "public operations", "recording fakes",
            "isolation is preserved", "Boundary isolation", "failure simulation",
            "framework integration", "justify retaining patching",
            "Do not add abstractions merely to eliminate mocks",
        ):
            assert phrase in message
