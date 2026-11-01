import json
import os
import subprocess
from pathlib import Path
from typing import NamedTuple, TypedDict, cast

import pytest


PATCH_RULE = "python.tests.review-patching"
PRIVATE_RULE = "python.tests.review-private-monkeypatch"
MUTABLE_DEFAULT_RULE = "python.tests.no-mutable-parameter-defaults"
TRUTHINESS_RULE = "python.tests.review-container-truthiness-default"
PRINT_RULE = "python.no-print-use-typer-output"


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
REVIEWED_BOUNDARY_OPERATIONS = (
    (
        "oidc_discovery",
        '("fastmcp.server.auth.oidc_proxy.httpx2.get", return_value=discovery_response)',
    ),
    ("uvicorn_failure", '("umbod.rest.metrics.http_server.Server", FailingServer)'),
    ("uvicorn_capture", '("umbod.rest.metrics.http_server.Server", CapturingServer)'),
    ("uvicorn_restart", '("umbod.rest.metrics.http_server.Server", RestartableServer)'),
    ("uvicorn_config", '("umbod.rest.metrics.http_server.Config", CapturingConfig)'),
)
REVIEWED_BOUNDARY_CASES = tuple(
    ScanCase(
        f"reviewed_boundary_{import_name}_{name}",
        f"tests/test_reviewed_boundary_{import_name}_{name}.py",
        f"{import_source}\n{patch_name}{operation}\n",
        (),
    )
    for import_name, import_source, patch_name in PATCH_IMPORTS
    if not import_name.startswith("legacy")
    for name, operation in REVIEWED_BOUNDARY_OPERATIONS
)
UNREVIEWED_BOUNDARY_OPERATIONS = (
    (
        "other_oidc_method",
        '("fastmcp.server.auth.oidc_proxy.httpx2.post", return_value=discovery_response)',
    ),
    (
        "other_oidc_replacement",
        '("fastmcp.server.auth.oidc_proxy.httpx2.get", side_effect=RuntimeError)',
    ),
    ("other_uvicorn_server", '("umbod.rest.metrics.http_server.Server", OtherServer)'),
    ("other_uvicorn_config", '("umbod.rest.metrics.http_server.Config", OtherConfig)'),
    (
        "application_behavior",
        '("umbod.rest.metrics.http_server.create_rest_metrics_app", CapturingConfig)',
    ),
)
UNREVIEWED_BOUNDARY_CASES = tuple(
    ScanCase(
        f"unreviewed_boundary_{name}",
        f"tests/test_unreviewed_boundary_{name}.py",
        f"from unittest.mock import patch\npatch{operation}\n",
        (PATCH_RULE,),
    )
    for name, operation in UNREVIEWED_BOUNDARY_OPERATIONS
)
MIXED_BOUNDARY_CASES = tuple(
    ScanCase(
        f"mixed_boundary_{name}",
        f"tests/test_mixed_boundary_{name}.py",
        f"from unittest.mock import patch\npatch{operation}\n"
        'patch("umbod.core.invocation.policy.ConnectorInvocation.create")\n',
        (PATCH_RULE,),
    )
    for name, operation in REVIEWED_BOUNDARY_OPERATIONS
)
CASES = (
    PATCH_CASES + FIXTURE_CASES + PRIVATE_CASES + NEGATIVE_CASES + SCOPE_CASES
    + REVIEWED_BOUNDARY_CASES + UNREVIEWED_BOUNDARY_CASES + MIXED_BOUNDARY_CASES
)


TEST_PATHS = (
    "tests/helpers.py",
    "package/tests/helpers.py",
    "live_runtime_tests/helpers.py",
    "package/live_runtime_tests/helpers.py",
    "package/test_service.py",
    "package/service_test.py",
    "package/conftest.py",
    "api/src/tests/helpers.py",
    "frontend/src/live_runtime_tests/helpers.py",
    "package/src/test_service.py",
    "package/src/service_test.py",
    "package/src/conftest.py",
)
SOURCE_PATHS = (
    "api/src/service.py",
    "frontend/src/service.py",
    "package/src/service.py",
    "src/service.py",
)
DESIGN_OPERATIONS = (
    (
        "parameter_default",
        "def resolve(value: int = 1) -> int:\n    return value\n",
        "python.no-parameter-default-values",
    ),
    (
        "dataclass_method",
        "from dataclasses import dataclass\n@dataclass\nclass {class_name}:\n"
        "    value: int\n    def resolve(self) -> int:\n        return self.value\n",
        "dataclass-with-methods",
    ),
    (
        "dataclass_nullable",
        "from dataclasses import dataclass\nfrom typing import Optional\n"
        "@dataclass\nclass {class_name}:\n    value: Optional[int]\n",
        "python.dataclass.none-type-field",
    ),
    (
        "pydantic_nullable",
        "from pydantic import BaseModel\nclass {class_name}(BaseModel):\n    value: int | None\n",
        "python.pydantic.none-type-field",
    ),
    (
        "argument_nullable",
        "from typing import Optional\ndef resolve(value: Optional[int]) -> int:\n"
        "    return value if value is not None else 1\n",
        "python.function-argument-none-type",
    ),
)
DESIGN_CASES = tuple(
    ScanCase(
        f"design_{operation}_{class_name}_{index}",
        f"design/{operation}/{class_name}/{path}",
        source.format(class_name=class_name),
        (rule,) if path in SOURCE_PATHS else (),
    )
    for operation, source, rule in DESIGN_OPERATIONS
    for class_name in ("Service", "TestService")
    for index, path in enumerate(SOURCE_PATHS + TEST_PATHS + ("package/service.py",))
)
MUTABLE_DEFAULTS = (
    ("empty_dict", "{}"),
    ("literal_dict", '{"key": 1}'),
    ("empty_list", "[]"),
    ("literal_list", "[1]"),
    ("literal_set", "{1}"),
    ("dict_comprehension", "{value: value for value in range(2)}"),
    ("list_comprehension", "[value for value in range(2)]"),
    ("set_comprehension", "{value for value in range(2)}"),
    ("dict_constructor", "dict()"),
    ("list_constructor", "list()"),
    ("set_constructor", "set()"),
    ("populated_dict_constructor", "dict(key=1)"),
    ("populated_list_constructor", "list((1, 2))"),
    ("populated_set_constructor", "set((1, 2))"),
)
MUTABLE_CASES = tuple(
    ScanCase(
        f"mutable_{name}_{index}",
        f"correctness/mutable/{name}/{path}",
        f"def resolve(value: object = {default}) -> object:\n    return value\n",
        (MUTABLE_DEFAULT_RULE,) if path in TEST_PATHS else ("python.no-parameter-default-values",),
    )
    for name, default in MUTABLE_DEFAULTS
    for index, path in enumerate(TEST_PATHS + SOURCE_PATHS)
)
CONTAINER_TYPES = (
    "dict[str, int]", "list[int]", "set[int]", "Mapping[str, int]", "Sequence[int]",
)
TRUTHINESS_CASES = tuple(
    ScanCase(
        f"truthiness_{container_index}_{annotation_name}_{path_index}",
        f"correctness/truthiness/{container_index}/{annotation_name}/{path}",
        "from typing import Optional, Mapping, Sequence\n"
        f"def resolve(value: {annotation}, fallback: object) -> object:\n"
        "    return value or fallback\n",
        (TRUTHINESS_RULE,) if path in TEST_PATHS else ("python.function-argument-none-type",),
    )
    for container_index, container in enumerate(CONTAINER_TYPES)
    for annotation_name, annotation in (
        ("optional", f"Optional[{container}]"), ("union", f"{container} | None"),
    )
    for path_index, path in enumerate(TEST_PATHS + SOURCE_PATHS)
)
SAFE_DEFAULTS = ("None", "1", '"value"', "True", "(1, 2)", "frozenset()")
SAFE_DEFAULT_CASES = tuple(
    ScanCase(
        f"safe_default_{default_index}_{path_index}",
        f"correctness/safe/{default_index}/{path}",
        f"def resolve(value: object = {default}) -> object:\n    return value\n",
        (),
    )
    for default_index, default in enumerate(SAFE_DEFAULTS)
    for path_index, path in enumerate(TEST_PATHS)
)
EXPLICIT_RESOLVER_CASES = tuple(
    ScanCase(
        f"explicit_none_{container_index}_{path_index}",
        f"correctness/resolver/{container_index}/{path}",
        "from typing import Optional, Mapping, Sequence\n"
        f"def resolve(value: Optional[{container}], fallback: object) -> object:\n"
        "    return fallback if value is None else value\n",
        (),
    )
    for container_index, container in enumerate(CONTAINER_TYPES)
    for path_index, path in enumerate(TEST_PATHS)
)
NONEMPTY_FALLBACK_CASES = tuple(
    ScanCase(
        f"nonempty_fallback_{fallback_index}_{path_index}",
        f"correctness/nonempty_fallback/{fallback_index}/{path}",
        "from typing import Optional\n"
        "def resolve(value: Optional[dict[str, int]]) -> object:\n"
        f"    return value or {fallback}\n",
        (TRUTHINESS_RULE,),
    )
    for fallback_index, fallback in enumerate(('{"key": 1}', "[1]", "{1}"))
    for path_index, path in enumerate(TEST_PATHS)
)
EMPTY_FALLBACK_CASES = tuple(
    ScanCase(
        f"empty_fallback_{fallback_index}_{path_index}",
        f"correctness/empty_fallback/{fallback_index}/{path}",
        "from typing import Optional\n"
        "def resolve(value: Optional[dict[str, int]]) -> object:\n"
        f"    return value or {fallback}\n",
        (),
    )
    for fallback_index, fallback in enumerate(("{}", "[]", "dict()", "list()", "set()"))
    for path_index, path in enumerate(TEST_PATHS)
)
PRINT_CASES = tuple(
    ScanCase(f"shared_print_{index}", f"shared_print/{path}", 'print("value")\n', (PRINT_RULE,))
    for index, path in enumerate(SOURCE_PATHS + ("api/tests/helpers.py", "api/src/tests/helpers.py"))
)
DESIGN_CORRECTNESS_CASES = (
    DESIGN_CASES + MUTABLE_CASES + TRUTHINESS_CASES + SAFE_DEFAULT_CASES
    + EXPLICIT_RESOLVER_CASES + EMPTY_FALLBACK_CASES + NONEMPTY_FALLBACK_CASES + PRINT_CASES
)
ALL_CASES = CASES + DESIGN_CORRECTNESS_CASES


EXTERNAL_SCOPE_CASES = (
    SCOPE_CASES
    + tuple(case for case in DESIGN_CASES if "/TestService/" in case.path)
    + tuple(case for case in MUTABLE_CASES if "/empty_dict/" in case.path)
    + tuple(case for case in TRUTHINESS_CASES if "/0/optional/" in case.path)
    + PRINT_CASES
)


def scan_cases(
    tmp_path_factory: pytest.TempPathFactory,
    cases: tuple[ScanCase, ...],
    explicit_file_targets: bool,
) -> dict[str, list[Finding]]:
    repository_root = Path(__file__).resolve().parents[3]
    fixture_root = tmp_path_factory.mktemp("semgrep_test_practices")
    (fixture_root / ".semgrepignore").write_text(
        (repository_root / ".semgrepignore").read_text(encoding="utf-8"), encoding="utf-8"
    )
    for case in cases:
        source_path = fixture_root / case.path
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(case.source, encoding="utf-8")
    targets = (
        [str(fixture_root)] if not explicit_file_targets
        else [str(fixture_root / case.path) for case in cases]
    )
    environment = dict(os.environ)
    environment.pop("VIRTUAL_ENV", None)
    result = subprocess.run(
        [
            "uv", "run", "--project", str(repository_root / "umbod"), "--locked",
            "semgrep", "scan", "--config", str(repository_root / ".semgrep.yml"),
            "--config", str(repository_root / ".semgrep/production-design.yml"),
            "--config", str(repository_root / ".semgrep/test-correctness.yml"),
            "--no-rewrite-rule-ids", "--json", "--metrics=off", "--disable-version-check",
            "--jobs=1", "--project-root", str(fixture_root), *targets,
        ],
        cwd=repository_root,
        env=environment,
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
    assert scanned_paths <= {case.path for case in cases}
    assert {case.path for case in cases if case.expected_rules} <= scanned_paths
    findings: dict[str, list[Finding]] = {case.path: [] for case in cases}
    for finding in scan["results"]:
        relative_path = Path(finding["path"]).relative_to(fixture_root).as_posix()
        findings[relative_path].append(finding)
    return findings


@pytest.fixture(scope="module")
def findings_by_case(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, list[Finding]]:
    return scan_cases(tmp_path_factory, ALL_CASES, False)


@pytest.fixture(scope="module")
def external_scope_findings(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, list[Finding]]:
    return scan_cases(tmp_path_factory, EXTERNAL_SCOPE_CASES, True)


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


@pytest.mark.parametrize(
    "case", DESIGN_CORRECTNESS_CASES, ids=[case.name for case in DESIGN_CORRECTNESS_CASES]
)
def test_shared_rules_separate_production_design_from_test_correctness(
    case: ScanCase, findings_by_case: dict[str, list[Finding]]
) -> None:
    findings = findings_by_case[case.path]
    assert sorted(finding["check_id"] for finding in findings) == sorted(case.expected_rules)
    error_rules = {MUTABLE_DEFAULT_RULE, PRINT_RULE, "python.no-parameter-default-values"}
    for finding in findings:
        expected_severity = "ERROR" if finding["check_id"] in error_rules else "WARNING"
        assert finding["extra"]["severity"] == expected_severity
        assert finding["extra"]["message"]

@pytest.mark.parametrize("case", EXTERNAL_SCOPE_CASES, ids=[case.name for case in EXTERNAL_SCOPE_CASES])
def test_rules_preserve_path_scope_for_external_file_targets(
    case: ScanCase, external_scope_findings: dict[str, list[Finding]]
) -> None:
    findings = external_scope_findings[case.path]
    assert sorted(finding["check_id"] for finding in findings) == sorted(case.expected_rules)
