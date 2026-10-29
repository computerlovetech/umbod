import json
from uuid import uuid4

from umbod.core.configuration.persistence import TextCipher
from umbod.core.messaging.discovery_events import connector_discovery_changed_event
from umbod.core.messaging.stores.event_stream import append_event_in_session
from umbod.core.persistence import AllOf, Database, DatabaseSession, Equals, TransactionMode, UpsertCommand

from ..personal_connections.models import PersonalConnectionKey
from ..personal_connections.runtime_models import PersonalRuntimeAuthorizationQuery, PersonalRuntimeTarget, PersonalRuntimeUnavailable
from ..personal_tools import (
    AdmitPersonalTool,
    MissingInventoryRevision,
    PersonalInventoryRevision,
    PersonalToolAdmission,
    PersonalToolObservation,
    PersonalToolRecord,
    PresentInventoryRevision,
    SavePersonalToolObservation,
    contract_fingerprint,
)
from ..personal_connections.health_models import RejectPersonalAuthorization
from .personal_authorization_rejections import record_rejection
from .personal_runtime_authorizations import load_personal_runtime_target
from .queries import query_all as _query
from .personal_tools_schema import (
    PERSONAL_TOOL_OBSERVATION_CONNECTOR_ID,
    PERSONAL_TOOL_OBSERVATION_NAMESPACE,
    PERSONAL_TOOL_OBSERVATION_SUBJECT,
    PERSONAL_TOOL_OBSERVATION_TABLE,
    PersonalToolObservationRecord,
    PersonalToolObservationRecordKey,
)
from .ports import CONNECTOR_DEFINITION_ADAPTER
from .schema import CONNECTOR_DEFINITION_CONNECTOR_ID, CONNECTOR_DEFINITION_TABLE


class EncryptedPersonalToolAccessStore:
    def __init__(self, database: Database, cipher: TextCipher) -> None:
        self._database = database
        self._cipher = cipher

    async def reject_authorization(self, command: RejectPersonalAuthorization) -> None:
        await record_rejection(self._database, self._cipher, command)

    async def _observation(self, session: DatabaseSession, query: PersonalRuntimeAuthorizationQuery) -> PersonalToolObservation | None:
        row = await session.find_one(PERSONAL_TOOL_OBSERVATION_TABLE, _query(AllOf((Equals(PERSONAL_TOOL_OBSERVATION_CONNECTOR_ID, query.key.connector_id), Equals(PERSONAL_TOOL_OBSERVATION_NAMESPACE, query.key.principal.namespace), Equals(PERSONAL_TOOL_OBSERVATION_SUBJECT, query.key.principal.subject)))))
        if row is None:
            return None
        document = json.loads(self._cipher.decrypt(row.document))
        if PersonalConnectionKey.model_validate(document["key"]) != query.key:
            raise PersonalRuntimeUnavailable("Personal inventory unavailable")
        if "version" not in document and "matches" in document and "contract_revision" in document:
            return None
        return PersonalToolObservation.model_validate(document)

    async def _inventory_revision(self, session: DatabaseSession, query: PersonalRuntimeAuthorizationQuery) -> PersonalInventoryRevision:
        observation = await self._observation(session, query)
        if observation is None:
            return MissingInventoryRevision(kind="missing")
        return PresentInventoryRevision(kind="present", revision=observation.inventory_revision)

    async def read_inventory_revision(self, query: PersonalRuntimeAuthorizationQuery) -> PersonalInventoryRevision:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            try:
                await load_personal_runtime_target(session, self._cipher, query)
                return await self._inventory_revision(session, query)
            except Exception:
                raise PersonalRuntimeUnavailable("Personal inventory unavailable") from None

    async def save_observation(self, command: SavePersonalToolObservation) -> None:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            target = await load_personal_runtime_target(session, self._cipher, command.query)
            try:
                revision = await self._inventory_revision(session, command.query)
            except Exception:
                raise PersonalRuntimeUnavailable("Personal inventory unavailable") from None
            if target != command.target or revision != command.expected_inventory_revision:
                raise PersonalRuntimeUnavailable("Personal discovery became stale")
            if command.expires_at > target.expires_at or command.expires_at <= command.query.now:
                raise PersonalRuntimeUnavailable("Invalid personal observation")
            observation = PersonalToolObservation(version=2, key=target.key, authorization_revision=target.authorization_revision, configuration_revision=target.configuration_revision, inventory_revision=str(uuid4()), tools=command.tools, expires_at=command.expires_at)
            key = PersonalToolObservationRecordKey(namespace=target.key.principal.namespace, subject=target.key.principal.subject, connector_id=target.key.connector_id)
            await session.upsert(PERSONAL_TOOL_OBSERVATION_TABLE, UpsertCommand(key=key, row=PersonalToolObservationRecord(**key.model_dump(), document=self._cipher.encrypt(observation.model_dump_json()))))
            await append_event_in_session(session, connector_discovery_changed_event("downstream_mcp", target.key.connector_id))

    async def list_available(self, query: PersonalRuntimeAuthorizationQuery) -> tuple[PersonalToolRecord, ...]:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            try:
                target = await load_personal_runtime_target(session, self._cipher, query)
                return await self._available(session, query, target)
            except Exception:
                return ()

    async def _available(self, session: DatabaseSession, query: PersonalRuntimeAuthorizationQuery, target: PersonalRuntimeTarget) -> tuple[PersonalToolRecord, ...]:
        observation = await self._observation(session, query)
        if observation is None:
            return ()
        if (
            observation.authorization_revision != target.authorization_revision
            or observation.configuration_revision != target.configuration_revision
            or observation.expires_at <= query.now
            or observation.expires_at > target.expires_at
        ):
            return ()
        definition_row = await session.find_one(CONNECTOR_DEFINITION_TABLE, _query(Equals(CONNECTOR_DEFINITION_CONNECTOR_ID, query.key.connector_id)))
        if definition_row is None:
            return ()
        definition = CONNECTOR_DEFINITION_ADAPTER.validate_python(definition_row.document)
        return tuple(
            PersonalToolRecord(definition=definition, tool=tool, inventory_revision=observation.inventory_revision, fingerprint=contract_fingerprint(tool))
            for tool in observation.tools
        )

    async def admit(self, command: AdmitPersonalTool) -> PersonalToolAdmission:
        identity = command.identity
        if identity.connector_kind != "downstream_mcp" or identity.capability_kind != "tool" or identity.connector_id != command.query.key.connector_id:
            raise PersonalRuntimeUnavailable("Personal tool unavailable")
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            try:
                target = await load_personal_runtime_target(session, self._cipher, command.query)
                records = await self._available(session, command.query, target)
                for record in records:
                    if record.tool.identity.downstream_name == identity.capability_key and record.inventory_revision == command.inventory_revision and record.fingerprint == command.fingerprint:
                        return PersonalToolAdmission(target=target, tool=record.tool)
            except Exception:
                raise PersonalRuntimeUnavailable("Personal tool unavailable") from None
            raise PersonalRuntimeUnavailable("Personal tool unavailable")
