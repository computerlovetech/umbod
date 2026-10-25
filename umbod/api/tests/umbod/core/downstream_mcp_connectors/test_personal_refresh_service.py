from tests.umbod.core.downstream_mcp_connectors.personal_caller_support import captured_personal_caller
import asyncio
from collections.abc import Callable

import pytest
from pydantic import SecretStr

from tests.umbod.core.downstream_mcp_connectors.test_personal_refresh import refresh_store, reservation
from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from umbod.core.connectors.downstream_mcp.personal_connections.authorization_models import authorize_personal_grant
from umbod.core.connectors.downstream_mcp.personal_connections.health_models import PersonalAuthorizationHealthQuery
from umbod.core.connectors.downstream_mcp.personal_connections.inventory_models import PersonalConnectorQuery, PersonalConnectorSelection
from umbod.core.connectors.downstream_mcp.personal_connections.models import Authorized
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_models import PersonalRefreshConflict, PersonalRefreshReconnectRequired, PersonalRefreshUnavailable
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_ports import PersonalRefreshStore
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_provider_models import PersonalOAuthRefreshDenied, RefreshPersonalOAuth
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_service import PersonalRefreshService

__all__ = ["runtime_case", "refresh_store"]


class AvailableInventory:
    async def get(self, query: PersonalConnectorQuery) -> PersonalConnectorSelection:
        return PersonalConnectorSelection(connector_id=query.connector_id, display_name="Personal", capability_description="Personal tools", enabled=True, has_authorization=True)


class ControlledRefreshProvider:
    def __init__(self, result: Callable[[RefreshPersonalOAuth], Authorized], hold: bool = False) -> None:
        self._result = result
        self._hold = hold
        self.started = asyncio.Event()
        self.commands: list[RefreshPersonalOAuth] = []

    async def refresh(self, command: RefreshPersonalOAuth) -> Authorized:
        self.commands.append(command)
        self.started.set()
        if self._hold:
            await asyncio.Event().wait()
        return self._result(command)


def service(case: RuntimeCase, store: PersonalRefreshStore, provider: ControlledRefreshProvider) -> PersonalRefreshService:
    return PersonalRefreshService(captured_personal_caller(case.query.key.principal, case.query.group_ids), AvailableInventory(), store, provider, lambda: case.query.now)


def success(command: RefreshPersonalOAuth) -> Authorized:
    return authorize_personal_grant(command.grant.model_copy(update={"access_token": SecretStr("renewed-token")}))


def denial(command: RefreshPersonalOAuth) -> Authorized:
    raise PersonalOAuthRefreshDenied("secret-raw-provider-error")


def operational_failure(command: RefreshPersonalOAuth) -> Authorized:
    raise RuntimeError("secret-raw-provider-error")


@pytest.mark.asyncio
async def test_service_exchanges_exactly_once_and_never_discovers(refresh_store: PersonalRefreshStore, runtime_case: RuntimeCase) -> None:
    provider = ControlledRefreshProvider(success)
    await service(runtime_case, refresh_store, provider).refresh("personal")
    assert len(provider.commands) == 1
    assert provider.commands[0].timeout_seconds == 20
    assert provider.commands[0].grant.key == runtime_case.query.key


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_result,expected,reason", [(denial, PersonalRefreshReconnectRequired, "refresh_denied"), (operational_failure, PersonalRefreshUnavailable, "refresh_uncertain")])
async def test_failure_is_secret_free_and_durable(refresh_store: PersonalRefreshStore, runtime_case: RuntimeCase, provider_result: Callable[[RefreshPersonalOAuth], Authorized], expected: type[Exception], reason: str) -> None:
    provider = ControlledRefreshProvider(provider_result)
    with pytest.raises(expected) as caught:
        await service(runtime_case, refresh_store, provider).refresh("personal")
    assert "secret-raw" not in str(caught.value)
    assert len(provider.commands) == 1
    health = await runtime_case.bundle.personal_authorization_health.get(PersonalAuthorizationHealthQuery(key=runtime_case.query.key, now=runtime_case.query.now))
    assert health.model_dump() == {"state": "reconnect_required", "reason": reason}


@pytest.mark.asyncio
async def test_actual_cancellation_is_preserved_after_durable_uncertainty(refresh_store: PersonalRefreshStore, runtime_case: RuntimeCase) -> None:
    provider = ControlledRefreshProvider(success, hold=True)
    task = asyncio.create_task(service(runtime_case, refresh_store, provider).refresh("personal"))
    await provider.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    health = await runtime_case.bundle.personal_authorization_health.get(PersonalAuthorizationHealthQuery(key=runtime_case.query.key, now=runtime_case.query.now))
    assert health.model_dump() == {"state": "reconnect_required", "reason": "refresh_uncertain"}
    assert len(provider.commands) == 1


@pytest.mark.asyncio
async def test_conflict_is_rejected_before_any_provider_contact(refresh_store: PersonalRefreshStore, runtime_case: RuntimeCase) -> None:
    await refresh_store.reserve(reservation(runtime_case))
    provider = ControlledRefreshProvider(success)
    with pytest.raises(PersonalRefreshConflict):
        await service(runtime_case, refresh_store, provider).refresh("personal")
    assert not provider.commands
