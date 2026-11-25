from umbod.core.configuration.persistence import TextCipher
from umbod.core.persistence import Database, ReadSession, AllOf, Equals

from ..models import uses_personal_oauth
from ..personal.connections import PersonalConnectionKey
from ..personal.tools import (
    PersonalToolDiscoveryQuery,
    PersonalToolObservation,
    PersonalToolRecord,
    contract_fingerprint,
)
from .personal_discovery_projection import DISCOVERY_AVAILABILITY_ADAPTER, AvailableDiscovery, BlockedRefresh, PreparingRefresh, discovery_filter
from .personal_discovery_schema import PERSONAL_DISCOVERY_TABLE
from .personal_tools_schema import PERSONAL_TOOL_OBSERVATION_TABLE, PERSONAL_TOOL_OBSERVATION_NAMESPACE, PERSONAL_TOOL_OBSERVATION_SUBJECT, PERSONAL_TOOL_OBSERVATION_CONNECTOR_ID
from .queries import query_all


class PersonalToolDiscoveryStore:
    def __init__(self, database: Database, cipher: TextCipher) -> None:
        self._database = database
        self._cipher = cipher

    async def read(self, query: PersonalToolDiscoveryQuery) -> tuple[PersonalToolRecord, ...]:
        return await self._read(query, executable_only=False)

    async def read_available(self, query: PersonalToolDiscoveryQuery) -> tuple[PersonalToolRecord, ...]:
        return await self._read(query, executable_only=True)

    async def _read(self, query: PersonalToolDiscoveryQuery, *, executable_only: bool) -> tuple[PersonalToolRecord, ...]:
        records: list[PersonalToolRecord] = []
        async with self._database.read_session() as session:
            for definition in query.definitions:
                if not uses_personal_oauth(definition):
                    continue
                key = PersonalConnectionKey(principal=query.principal, connector_id=definition.connector_id)
                try:
                    availability = await session.find_one(PERSONAL_DISCOVERY_TABLE, query_all(discovery_filter(key)))
                    if availability is None or (availability.namespace, availability.subject, availability.connector_id) != (key.principal.namespace, key.principal.subject, key.connector_id):
                        continue
                    state = DISCOVERY_AVAILABILITY_ADAPTER.validate_json(self._cipher.decrypt(availability.document))
                    if not isinstance(state, AvailableDiscovery) or state.key != key:
                        continue
                    if state.endpoint_url != definition.endpoint_url or state.issued_at > query.now or state.expires_at <= state.issued_at:
                        continue
                    if executable_only and (state.authorization_rejected or state.expires_at <= query.now or isinstance(state.refresh, BlockedRefresh) or isinstance(state.refresh, PreparingRefresh) and state.refresh.deadline > query.now):
                        continue
                    observation = await self._observation(session, key)
                    if observation is None or observation.configuration_revision != state.configuration_revision:
                        continue
                    if executable_only and (observation.expires_at <= query.now or observation.authorization_revision != state.authorization_revision):
                        continue
                    if observation.authorization_revision == state.authorization_revision:
                        if observation.expires_at <= state.issued_at or observation.expires_at > state.expires_at:
                            continue
                    elif observation.authorization_revision != state.expected_authorization_revision:
                        continue
                    records.extend(PersonalToolRecord(definition=definition, tool=tool, inventory_revision=observation.inventory_revision, fingerprint=contract_fingerprint(tool)) for tool in observation.tools)
                except Exception:
                    continue
        return tuple(records)

    async def _observation(self, session: ReadSession, key: PersonalConnectionKey) -> PersonalToolObservation | None:
        row = await session.find_one(PERSONAL_TOOL_OBSERVATION_TABLE, query_all(AllOf((Equals(PERSONAL_TOOL_OBSERVATION_NAMESPACE, key.principal.namespace), Equals(PERSONAL_TOOL_OBSERVATION_SUBJECT, key.principal.subject), Equals(PERSONAL_TOOL_OBSERVATION_CONNECTOR_ID, key.connector_id)))))
        if row is None:
            return None
        if (row.namespace, row.subject, row.connector_id) != (key.principal.namespace, key.principal.subject, key.connector_id):
            raise ValueError("Personal inventory ownership mismatch")
        observation = PersonalToolObservation.model_validate_json(self._cipher.decrypt(row.document))
        if observation.key != key:
            raise ValueError("Personal inventory ownership mismatch")
        return observation
