from datetime import UTC, datetime
from unittest.mock import AsyncMock

from pydantic import ValidationError

import pytest

from umbod.core.callers import AuthenticationProvenance, CallerContext, GroupMembership, UnavailableSubject
from umbod.core.connectors.downstream_mcp.personal_connections import CanonicalPrincipal, MissingCanonicalPrincipal, PersonalConnectionService
from umbod.core.connectors.downstream_mcp.personal_connections.caller import PersonalCaller, UnavailablePersonalCaller
from umbod.core.connectors.downstream_mcp.personal_connections.ports import PersonalConnectionStore
from umbod.core.connectors.downstream_mcp.personal_connections.inventory_ports import PersonalConnectorInventory
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_ports import PersonalOAuthAttemptStore, PersonalOAuthProvider
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_service import PersonalOAuthService
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_ports import PersonalRefreshStore
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_provider_ports import PersonalOAuthRefreshProvider
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_service import PersonalRefreshService
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import PersonalOAuthConfigurationStore
from umbod.core.connectors.downstream_mcp.stores.ports import ConnectorDefinitionStore


@pytest.mark.asyncio
async def test_unavailable_caller_rejects_before_owner_storage() -> None:
    store = AsyncMock(spec=PersonalConnectionStore)
    service = PersonalConnectionService(UnavailablePersonalCaller(kind="unavailable"), store)
    with pytest.raises(MissingCanonicalPrincipal):
        await service.get("connector")
    store.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_unavailable_caller_cannot_start_oauth_before_any_owner_lookup() -> None:
    inventory = AsyncMock(spec=PersonalConnectorInventory)
    connections = AsyncMock(spec=PersonalConnectionStore)
    attempts = AsyncMock(spec=PersonalOAuthAttemptStore)
    service = PersonalOAuthService(
        UnavailablePersonalCaller(kind="unavailable"), inventory,
        AsyncMock(spec=ConnectorDefinitionStore), connections, attempts,
        AsyncMock(spec=PersonalOAuthProvider), "https://umbod.example/callback",
        lambda: datetime.now(UTC), AsyncMock(spec=PersonalOAuthConfigurationStore),
    )
    with pytest.raises(MissingCanonicalPrincipal):
        await service.start("connector")
    assert inventory.mock_calls == connections.mock_calls == attempts.mock_calls == []


@pytest.mark.asyncio
async def test_unavailable_caller_cannot_reserve_refresh() -> None:
    inventory = AsyncMock(spec=PersonalConnectorInventory)
    store = AsyncMock(spec=PersonalRefreshStore)
    service = PersonalRefreshService(
        UnavailablePersonalCaller(kind="unavailable"), inventory, store,
        AsyncMock(spec=PersonalOAuthRefreshProvider), lambda: datetime.now(UTC),
    )
    with pytest.raises(MissingCanonicalPrincipal):
        await service.refresh("connector")
    assert inventory.mock_calls == store.mock_calls == []


def test_unavailable_caller_requires_explicit_state_and_forbids_extra_data() -> None:
    with pytest.raises(ValidationError):
        UnavailablePersonalCaller.model_validate({})
    with pytest.raises(ValidationError):
        UnavailablePersonalCaller.model_validate({"kind": "unavailable", "principal": "raw"})
    with pytest.raises(ValidationError):
        UnavailablePersonalCaller(kind="unavailable").kind = "other"


@pytest.mark.asyncio
async def test_authenticated_caller_without_raw_subject_uses_canonical_owner() -> None:
    store = AsyncMock(spec=PersonalConnectionStore)
    owner = CanonicalPrincipal(namespace="entra", subject="tenant:object")
    caller = PersonalCaller(
        caller=CallerContext(authentication=AuthenticationProvenance.UPSTREAM_VERIFIED, subject=UnavailableSubject(kind="unavailable")),
        principal=owner,
        groups=GroupMembership(group_ids=("team",)),
    )
    await PersonalConnectionService(caller, store).get("connector")
    assert store.get.await_args.args[0].principal == owner


@pytest.mark.asyncio
async def test_unavailable_authentication_cannot_use_resolved_owner() -> None:
    store = AsyncMock(spec=PersonalConnectionStore)
    caller = PersonalCaller(
        caller=CallerContext(authentication=AuthenticationProvenance.UNAVAILABLE, subject=UnavailableSubject(kind="unavailable")),
        principal=CanonicalPrincipal(namespace="trusted", subject="owner"),
        groups=GroupMembership(group_ids=()),
    )
    with pytest.raises(MissingCanonicalPrincipal):
        await PersonalConnectionService(caller, store).get("connector")
    store.get.assert_not_awaited()
