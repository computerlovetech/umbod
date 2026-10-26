import asyncio
import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from typer.testing import CliRunner

from umbod.cli.filesystem.ports import BootstrapPolicySource
from umbod.cli.filesystem.service import bootstrap_root
from umbod.cli.main import app
from umbod.config import load_app_config
from umbod.core.filesystem import (
    SYSTEM_ROOT_OWNER,
    Ownership,
    Permission,
    Principal,
    PrincipalType,
    RootBootstrapGrant,
    RootBootstrapSpec,
    RootProvisioning,
)
from umbod.core.persistence import PersistenceRuntime, PersistenceRuntimeProvider
from umbod.infrastructure import (
    ConfiguredPersistenceRuntimeProvider,
    create_access_control_driver,
    create_namespace_driver,
)


class MemoryBootstrapPolicySource:
    def __init__(self, spec: RootBootstrapSpec) -> None:
        self._spec = spec

    def load(self, policy_file: str) -> RootBootstrapSpec:
        return self._spec


@pytest.fixture
def bootstrap_policy() -> RootBootstrapSpec:
    source: BootstrapPolicySource = MemoryBootstrapPolicySource(
        RootBootstrapSpec(grants=(RootBootstrapGrant(
            principal=Principal(type=PrincipalType.GROUP, issuer="trusted-issuer", id="private-group"),
            permissions=frozenset({Permission.READ, Permission.SHARE}),
        ),))
    )
    return source.load("trusted-policy")


@pytest.fixture
def policy_file(tmp_path: Path, bootstrap_policy: RootBootstrapSpec) -> Path:
    path = tmp_path / "private-policy.json"
    path.write_text(bootstrap_policy.model_dump_json())
    return path


@pytest.fixture(autouse=True)
def configured_sqlite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UMBOD_CONNECTOR_STORE", "sqlite")
    monkeypatch.setenv("UMBOD_CONNECTOR_STORE_SQLITE_PATH", str(tmp_path / "configured.sqlite3"))


async def prepared_runtime() -> PersistenceRuntime:
    runtime = ConfiguredPersistenceRuntimeProvider(load_app_config(".env").connector_store).create()
    await runtime.readiness.ensure_ready()
    return runtime


@pytest.fixture
def tracked_shutdown(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[AsyncMock]]:
    shutdowns: list[AsyncMock] = []
    create = ConfiguredPersistenceRuntimeProvider.create

    def create_tracked(provider: ConfiguredPersistenceRuntimeProvider) -> PersistenceRuntime:
        runtime = create(provider)
        shutdown = AsyncMock(wraps=runtime.shutdown)
        monkeypatch.setattr(type(runtime), "shutdown", shutdown)
        shutdowns.append(shutdown)
        return runtime

    monkeypatch.setattr(ConfiguredPersistenceRuntimeProvider, "create", create_tracked)
    yield shutdowns


def test_bootstrap_creates_system_root_in_configured_database_and_closes_runtime(
    policy_file: Path,
    bootstrap_policy: RootBootstrapSpec,
    tracked_shutdown: list[AsyncMock],
    tmp_path: Path,
) -> None:
    result = CliRunner().invoke(app, ["filesystem", "bootstrap", "--policy-file", str(policy_file)])

    assert result.exit_code == 0, result.output
    assert result.output == "Filesystem root bootstrap completed. Bootstrap does not reconcile existing grants.\n"
    tracked_shutdown[0].assert_awaited_once()
    assert (tmp_path / "configured.sqlite3").exists()

    async def inspect_root() -> None:
        runtime = await prepared_runtime()
        try:
            root = await create_namespace_driver(database=runtime.database).get_root()
            access = create_access_control_driver(database=runtime.database)
            assert (await access.get_owner(root.id)).owner == SYSTEM_ROOT_OWNER
            grants = await access.list_grants(root.id)
            assert len(grants) == 1
            assert grants[0].principal == bootstrap_policy.grants[0].principal
            assert grants[0].permissions == set(bootstrap_policy.grants[0].permissions)
            assert grants[0].recursive is False
        finally:
            await runtime.shutdown()

    asyncio.run(inspect_root())


def test_bootstrap_replay_preserves_revoked_grants(policy_file: Path, bootstrap_policy: RootBootstrapSpec) -> None:
    command = ["filesystem", "bootstrap", "--policy-file", str(policy_file)]
    assert CliRunner().invoke(app, command).exit_code == 0

    async def revoke() -> None:
        runtime = await prepared_runtime()
        try:
            root = await create_namespace_driver(database=runtime.database).get_root()
            await create_access_control_driver(database=runtime.database).remove_grant(
                root.id, bootstrap_policy.grants[0].principal,
            )
        finally:
            await runtime.shutdown()

    asyncio.run(revoke())
    result = CliRunner().invoke(app, command)
    assert result.exit_code == 0
    assert "does not reconcile existing grants" in result.output

    async def inspect_grants() -> None:
        runtime = await prepared_runtime()
        try:
            root = await create_namespace_driver(database=runtime.database).get_root()
            assert not await create_access_control_driver(database=runtime.database).list_grants(root.id)
        finally:
            await runtime.shutdown()

    asyncio.run(inspect_grants())


@pytest.mark.parametrize("payload", [
    "invalid private-group JSON",
    "{}",
    '{"grants": [{"principal": {"type": "group", "id": "private-group"}, "permissions": []}]}',
    '{"grants": [{"principal": {"type": "group", "issuer": "private-group"}, "permissions": []}]}',
    '{"grants": [{"principal": {"type": "group", "issuer": "private-group", "id": "id"}, "permissions": ["admin"]}]}',
    '{"grants": [], "owner": "private-group"}',
    '{"grants": [{"principal": {"type": "group", "issuer": "private-group", "id": "id"}}]}',
    '{"grants": [{"principal": {"type": "system", "issuer": "issuer", "id": "private-group"}, "permissions": []}]}',
    '{"grants": [{"principal": {"type": "user", "issuer": "issuer", "id": "private-group"}, "permissions": [], "recursive": true}]}',
    '{"grants": [{"principal": {"type": "user", "issuer": "issuer", "id": "private-group", "secret": true}, "permissions": []}]}',
])
def test_invalid_policy_fails_before_configuration_or_persistence(
    payload: str, policy_file: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_file.write_text(payload)
    load_config = Mock(side_effect=AssertionError("configuration must not be loaded"))
    provider = Mock(side_effect=AssertionError("persistence must not be opened"))
    monkeypatch.setattr("umbod.cli.filesystem.command.load_app_config", load_config)
    monkeypatch.setattr("umbod.cli.filesystem.command.ConfiguredPersistenceRuntimeProvider", provider)

    result = CliRunner().invoke(app, ["filesystem", "bootstrap", "--policy-file", str(policy_file)])

    assert result.exit_code == 1
    assert result.output == "Bootstrap policy could not be read or is invalid. Supply a valid trusted JSON policy file.\n"
    load_config.assert_not_called()
    provider.assert_not_called()


def test_policy_file_is_required() -> None:
    result = CliRunner().invoke(app, ["filesystem", "bootstrap"])
    assert result.exit_code != 0
    assert "--policy-file" in result.output


@pytest.mark.parametrize("failure", [FileNotFoundError, PermissionError, IsADirectoryError])
def test_policy_io_errors_do_not_disclose_paths_or_details(
    failure: type[OSError], policy_file: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Path, "read_bytes", Mock(side_effect=failure("secret private-group path")))
    result = CliRunner().invoke(app, ["filesystem", "bootstrap", "--policy-file", str(policy_file)])
    assert result.exit_code == 1
    assert "could not be read or is invalid" in result.output
    assert str(policy_file) not in result.output
    assert "secret" not in result.output
    assert "private-group" not in result.output


def test_root_conflict_reports_operator_recovery_without_disclosing_identity(policy_file: Path) -> None:
    async def own_root() -> None:
        runtime = await prepared_runtime()
        try:
            root = await create_namespace_driver(database=runtime.database).get_root()
            await create_access_control_driver(database=runtime.database).set_owner(Ownership(
                node_id=root.id,
                owner=Principal(type=PrincipalType.USER, issuer="private-issuer", id="private-owner"),
            ))
        finally:
            await runtime.shutdown()

    asyncio.run(own_root())
    result = CliRunner().invoke(app, ["filesystem", "bootstrap", "--policy-file", str(policy_file)])
    assert result.exit_code == 1
    assert "conflict" in result.output
    assert "explicit migration or recovery" in result.output
    assert "private-owner" not in result.output
    assert "private-issuer" not in result.output


@pytest.mark.parametrize("stage", ["readiness", "provision"])
@pytest.mark.parametrize("failure", [RuntimeError("secret private-group path"), asyncio.CancelledError()])
def test_bootstrap_shuts_down_runtime_on_failure_or_cancellation(
    stage: str, failure: BaseException, bootstrap_policy: RootBootstrapSpec, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = Mock(spec=PersistenceRuntime)
    runtime.readiness.ensure_ready = AsyncMock()
    runtime.shutdown = AsyncMock()
    provider = Mock(spec=PersistenceRuntimeProvider)
    provider.create.return_value = runtime
    provisioning = Mock(spec=RootProvisioning)
    provisioning.provision = AsyncMock()
    monkeypatch.setattr("umbod.cli.filesystem.service.create_root_provisioning", Mock(return_value=provisioning))
    operation = runtime.readiness.ensure_ready if stage == "readiness" else provisioning.provision
    operation.side_effect = failure

    with pytest.raises(type(failure)):
        asyncio.run(bootstrap_root(bootstrap_policy, provider))

    runtime.shutdown.assert_awaited_once()
    if stage == "readiness":
        provisioning.provision.assert_not_awaited()


@pytest.mark.parametrize("stage", ["config", "create", "readiness", "provision", "shutdown"])
def test_command_sanitizes_configuration_and_persistence_failures(
    stage: str, policy_file: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("secret private-group /private/path")
    runtime = Mock(spec=PersistenceRuntime)
    runtime.readiness.ensure_ready = AsyncMock()
    runtime.shutdown = AsyncMock()
    provider = Mock(spec=PersistenceRuntimeProvider)
    provider.create.return_value = runtime
    provisioning = Mock(spec=RootProvisioning)
    provisioning.provision = AsyncMock()
    monkeypatch.setattr("umbod.cli.filesystem.command.ConfiguredPersistenceRuntimeProvider", Mock(return_value=provider))
    monkeypatch.setattr("umbod.cli.filesystem.service.create_root_provisioning", Mock(return_value=provisioning))
    operations = {
        "config": Mock(),
        "create": provider.create,
        "readiness": runtime.readiness.ensure_ready,
        "provision": provisioning.provision,
        "shutdown": runtime.shutdown,
    }
    if stage == "config":
        monkeypatch.setattr("umbod.cli.filesystem.command.load_app_config", operations[stage])
    operations[stage].side_effect = failure

    result = CliRunner().invoke(app, ["filesystem", "bootstrap", "--policy-file", str(policy_file)])

    assert result.exit_code == 1
    assert result.output == "Filesystem root bootstrap failed. Check configuration and persistence availability before retrying.\n"
    if stage in {"readiness", "provision", "shutdown"}:
        runtime.shutdown.assert_awaited_once()


def test_container_executable_accepts_explicit_stdin_policy_path(bootstrap_policy: RootBootstrapSpec) -> None:
    executable = Path(sys.executable).with_name("umbod")
    result = subprocess.run(
        [str(executable), "filesystem", "bootstrap", "--policy-file", "/dev/stdin"],
        input=bootstrap_policy.model_dump_json(),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "Filesystem root bootstrap completed. Bootstrap does not reconcile existing grants.\n"


def test_empty_policy_grants_are_accepted(policy_file: Path) -> None:
    policy_file.write_text(json.dumps({"grants": []}))
    result = CliRunner().invoke(app, ["filesystem", "bootstrap", "--policy-file", str(policy_file)])
    assert result.exit_code == 0, result.output
