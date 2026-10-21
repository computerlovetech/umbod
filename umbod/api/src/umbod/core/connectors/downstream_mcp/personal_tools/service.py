from collections.abc import Callable
from datetime import datetime

from ..personal_connections.runtime_models import PersonalAuthorizationRejected, PersonalRuntimeAuthorizationQuery, PersonalRuntimeUnavailable
from ..personal_connections.health_models import RejectPersonalAuthorization
from ..personal_connections.runtime_ports import PersonalMcpTransport, PersonalRuntimeAuthorizationStore
from ..stores.ports import ConnectorIdQuery
from .contract_validation import contract_fingerprint
from .models import PersonalToolDiscoveryResult, PersonalToolMatch, PersonalToolPolicy, SavePersonalToolObservation
from .ports import PersonalToolAccessStore, PersonalToolPolicyStore


class PersonalToolDiscoveryService:
    def __init__(
        self,
        policy_store: PersonalToolPolicyStore,
        authorization_store: PersonalRuntimeAuthorizationStore,
        access_store: PersonalToolAccessStore,
        transport: PersonalMcpTransport,
        clock: Callable[[], datetime],
    ) -> None:
        self._policies = policy_store
        self._authorizations = authorization_store
        self._access = access_store
        self._transport = transport
        self._clock = clock

    async def discover(self, query: PersonalRuntimeAuthorizationQuery) -> PersonalToolDiscoveryResult:
        policy = await self._policies.get(ConnectorIdQuery(connector_id=query.key.connector_id))
        if not isinstance(policy, PersonalToolPolicy):
            raise PersonalRuntimeUnavailable("Personal tool policy unavailable")
        target = await self._authorizations.resolve(query)
        try:
            inventory = await self._transport.list_tools(target)
        except PersonalAuthorizationRejected:
            await self._authorizations.reject_authorization(RejectPersonalAuthorization(
                key=target.key, expected_connection_revision=target.authorization_revision,
            ))
            raise PersonalRuntimeUnavailable("Personal discovery unavailable") from None
        approved = {tool.identity.downstream_name: contract_fingerprint(tool) for tool in policy.tools}
        matches = tuple(
            PersonalToolMatch(name=tool.identity.downstream_name, fingerprint=contract_fingerprint(tool))
            for tool in inventory.tools
            if tool.identity.connector_id == query.key.connector_id
            and approved.get(tool.identity.downstream_name) == contract_fingerprint(tool)
        )
        await self._access.save_observation(SavePersonalToolObservation(
            query=query.model_copy(update={"now": self._clock()}),
            target=target,
            contract_revision=policy.revision,
            matches=matches,
            expires_at=target.expires_at,
        ))
        return PersonalToolDiscoveryResult(status="observed", matched_count=len(matches))
