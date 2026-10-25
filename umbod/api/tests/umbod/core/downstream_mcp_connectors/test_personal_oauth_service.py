from tests.umbod.core.downstream_mcp_connectors.personal_caller_support import captured_personal_caller
import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr

from umbod.core.connectors.downstream_mcp.models import OAuthConnectorDefinition
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import PersonalOAuthConfigurationStore, PersonalOAuthConfiguration, legacy_personal_oauth_policy
from umbod.core.connectors.downstream_mcp.stores.ports import ConnectorDefinitionFound, ConnectorDefinitionStore
from umbod.core.connectors.downstream_mcp.personal_connections.inventory_models import PersonalConnectorSelection
from umbod.core.connectors.downstream_mcp.personal_connections.inventory_ports import PersonalConnectorInventory
from umbod.core.connectors.downstream_mcp.personal_connections.models import CanonicalPrincipal, PersonalConnection, PersonalConnectionKey, Unauthorized
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import PersonalOAuthConflict, PersonalOAuthProviderFailure, PreparedPersonalOAuth
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_ports import PersonalOAuthAttemptStore, PersonalOAuthProvider
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_service import PersonalOAuthService
from umbod.core.connectors.downstream_mcp.personal_connections.ports import PersonalConnectionStore


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def service_dependencies() -> tuple[PersonalOAuthService, AsyncMock, AsyncMock]:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    principal = CanonicalPrincipal(namespace="test:oauth", subject="alice")
    connections = AsyncMock(spec=PersonalConnectionStore)
    connections.get.return_value = PersonalConnection(
        key=PersonalConnectionKey(principal=principal, connector_id="connector"),
        enabled=True, authorization=Unauthorized(), revision="revision",
    )
    definitions = AsyncMock(spec=ConnectorDefinitionStore)
    definitions.get.return_value = ConnectorDefinitionFound(definition=OAuthConnectorDefinition(
        connector_id="connector", display_name="Personal", capability_description="Personal tools",
        endpoint_url="https://tools.example/mcp", public_path="/mcp/proxies/personal", authorization_mode="personal",
    ))
    inventory = AsyncMock(spec=PersonalConnectorInventory)
    inventory.get.return_value = PersonalConnectorSelection(
        connector_id="connector", display_name="Personal", capability_description="Personal tools",
        enabled=True, has_authorization=False,
    )
    attempts = AsyncMock(spec=PersonalOAuthAttemptStore)
    provider = AsyncMock(spec=PersonalOAuthProvider)
    configurations = AsyncMock(spec=PersonalOAuthConfigurationStore)
    configurations.get.return_value = PersonalOAuthConfiguration(connector_id="connector", policy=legacy_personal_oauth_policy())
    ticks = iter((now, now + timedelta(seconds=5), now + timedelta(seconds=10)))
    return PersonalOAuthService(
        captured_personal_caller(principal, ("team",)), inventory, definitions,
        connections, attempts, provider, "https://api.example/api/oauth/downstream-mcp/callback",
        lambda: next(ticks), configurations,
    ), attempts, provider


async def test_reservation_conflict_never_contacts_provider(
    service_dependencies: tuple[PersonalOAuthService, AsyncMock, AsyncMock],
) -> None:
    service, attempts, provider = service_dependencies
    attempts.reserve.side_effect = PersonalOAuthConflict()
    with pytest.raises(PersonalOAuthConflict):
        await service.start("connector")
    provider.prepare.assert_not_awaited()


@pytest.mark.parametrize("failure", [ValueError("secret-provider-error"), asyncio.CancelledError()])
async def test_failed_or_cancelled_preparation_aborts_reserved_attempt(
    service_dependencies: tuple[PersonalOAuthService, AsyncMock, AsyncMock], failure: BaseException,
) -> None:
    service, attempts, provider = service_dependencies
    provider.prepare.side_effect = failure
    expected = asyncio.CancelledError if isinstance(failure, asyncio.CancelledError) else PersonalOAuthProviderFailure
    with pytest.raises(expected):
        await service.start("connector")
    attempts.reserve.assert_awaited_once()
    attempts.abort_preparation.assert_awaited_once()
    attempts.publish.assert_not_awaited()


async def test_publication_uses_reserved_preparation_and_fresh_time(
    service_dependencies: tuple[PersonalOAuthService, AsyncMock, AsyncMock],
) -> None:
    service, attempts, provider = service_dependencies
    provider.prepare.return_value = PreparedPersonalOAuth(
        authorization_url=SecretStr("https://issuer.example/authorize"), context=SecretStr("secret-context"),
    )
    from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import PersonalOAuthAttemptView
    attempts.publish.return_value = PersonalOAuthAttemptView(
        attempt_id="a" * 32, status="pending", expires_at=datetime(2026, 1, 1, 0, 10, tzinfo=UTC),
    )
    result = await service.start("connector")
    reservation = attempts.reserve.call_args.args[0]
    publication = attempts.publish.call_args.args[0]
    assert provider.prepare.call_args.args[0] == reservation.preparation
    assert publication.query.now > reservation.created_at
    assert reservation.expires_at - reservation.created_at == timedelta(minutes=10)
    assert len(reservation.preparation.code_verifier.get_secret_value()) >= 43
    assert reservation.preparation.state.get_secret_value().startswith(reservation.attempt_id + ".")
    assert result.attempt.status == "pending"
