from collections.abc import Callable
from datetime import datetime

from ..personal_connections.runtime_models import PersonalAuthorizationRejected, PersonalRuntimeAuthorizationQuery, PersonalRuntimeUnavailable
from ..personal_connections.health_models import RejectPersonalAuthorization
from ..personal_connections.runtime_ports import PersonalMcpTransport, PersonalRuntimeAuthorizationStore
from .models import PersonalToolDiscoveryResult, SavePersonalToolObservation
from .ports import PersonalToolAccessStore


class PersonalToolDiscoveryService:
    def __init__(
        self,
        authorization_store: PersonalRuntimeAuthorizationStore,
        access_store: PersonalToolAccessStore,
        transport: PersonalMcpTransport,
        clock: Callable[[], datetime],
    ) -> None:
        self._authorizations = authorization_store
        self._access = access_store
        self._transport = transport
        self._clock = clock

    async def discover(self, query: PersonalRuntimeAuthorizationQuery) -> PersonalToolDiscoveryResult:
        target = await self._authorizations.resolve(query)
        revision = await self._access.read_inventory_revision(query)
        try:
            inventory = await self._transport.list_tools(target)
        except PersonalAuthorizationRejected:
            await self._authorizations.reject_authorization(RejectPersonalAuthorization(
                key=target.key, expected_connection_revision=target.authorization_revision,
            ))
            raise PersonalRuntimeUnavailable("Personal discovery unavailable") from None
        try:
            command = SavePersonalToolObservation(
                query=query.model_copy(update={"now": self._clock()}),
                target=target,
                expected_inventory_revision=revision,
                tools=inventory.tools,
                expires_at=target.expires_at,
            )
        except ValueError:
            raise PersonalRuntimeUnavailable("Personal discovery unavailable") from None
        await self._access.save_observation(command)
        return PersonalToolDiscoveryResult(status="observed", tool_count=len(inventory.tools))
