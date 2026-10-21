from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from tests.persistence_runtime import prepared_sqlite_runtime
from tests.umbod.core.downstream_mcp_connectors.test_unit_of_work_contract import (
    AggregateHarness,
    _inmemory,
    _sqlite,
)
from umbod.core.connectors.downstream_mcp.connection import DownstreamMcpConnectionConfiguration
from umbod.core.connectors.downstream_mcp.errors import (
    DownstreamConnectorConflictError,
    DownstreamPublicPathConflictError,
)
from umbod.core.connectors.downstream_mcp.management import (
    DownstreamConnectorCreator,
    DownstreamConnectorPreparation,
    DownstreamConnectorQueries,
)
from umbod.core.connectors.downstream_mcp.models import (
    CreatePersonalOAuthConnectorDefinition,
    OAuthCredentialState,
)
from umbod.core.connectors.downstream_mcp.probe import ProbeResult
from umbod.core.connectors.downstream_mcp.stores import (
    ConnectorIdQuery,
    SaveCredential,
)
from umbod.core.identity import ConnectorIdentity


class FixedIdentity:
    def __init__(self, connector_id: str) -> None:
        self._connector_id = connector_id

    def new_id(self) -> str:
        return self._connector_id

    async def ensure_available(self, requested: ConnectorIdentity) -> None:
        return None


class ForbiddenProbe:
    async def probe(self, configuration: DownstreamMcpConnectionConfiguration) -> ProbeResult:
        raise AssertionError("Personal creation must not probe")


def creator(harness: AggregateHarness, connector_id: str) -> DownstreamConnectorCreator:
    identity = FixedIdentity(connector_id)
    return DownstreamConnectorCreator(
        harness.definitions,
        identity,
        identity,
        DownstreamConnectorPreparation(ForbiddenProbe()),
        harness.unit_of_work,
    )


def command() -> CreatePersonalOAuthConnectorDefinition:
    return CreatePersonalOAuthConnectorDefinition(
        display_name="Personal",
        capability_description="Personal connector capabilities",
        endpoint_url="https://personal.example/mcp",
        public_path="/mcp/proxies/personal",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("factory", (_inmemory, _sqlite), ids=("inmemory", "sqlite"))
@pytest.mark.parametrize("phase", ("definition", "credential", "catalog", "health", "activation", "publication", "personal_oauth_configuration", "personal_oauth_configuration_saved"))
async def test_personal_creation_failure_is_atomic(
    tmp_path: Path,
    factory: Callable[[Path, Callable[[str], None]], Awaitable[AggregateHarness]],
    phase: str,
) -> None:
    def fault(current: str) -> None:
        if current == phase:
            raise RuntimeError("injected failure")

    path = tmp_path / "personal.sqlite3"
    await prepared_sqlite_runtime(path)
    harness = await factory(path, fault)
    with pytest.raises(RuntimeError, match="injected failure"):
        await creator(harness, "personal").create_personal_oauth(command())
    query = ConnectorIdQuery(connector_id="personal")
    assert not (await harness.definitions.get(query)).found
    assert not (await harness.credentials.get(query)).found
    assert not (await harness.catalogs.get(query)).found
    assert not (await harness.health.get(query)).found
    assert not await harness.publishing.is_published("personal")


@pytest.mark.asyncio
async def test_personal_creation_enforces_id_and_path_uniqueness(tmp_path: Path) -> None:
    harness = await _inmemory(tmp_path, lambda phase: None)
    await creator(harness, "personal").create_personal_oauth(command())
    with pytest.raises(DownstreamConnectorConflictError):
        await creator(harness, "personal").create_personal_oauth(command())
    with pytest.raises(DownstreamPublicPathConflictError):
        await creator(harness, "other").create_personal_oauth(command())
    assert len((await harness.definitions.list()).definitions) == 1


@pytest.mark.asyncio
async def test_personal_credentials_projection_ignores_legacy_shared_authorization(tmp_path: Path) -> None:
    harness = await _inmemory(tmp_path, lambda phase: None)
    await creator(harness, "personal").create_personal_oauth(command())
    await harness.credentials.save(SaveCredential(credential=OAuthCredentialState(
        connector_id="personal", authorization="legacy-secret",
    )))
    queries = DownstreamConnectorQueries(
        harness.definitions, harness.credentials, harness.catalogs, harness.health, harness.publishing
    )
    assert not await queries.credential_configured("personal")
