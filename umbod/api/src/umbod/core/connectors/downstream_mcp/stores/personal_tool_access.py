from umbod.core.activation.stores.schema import (
    CAPABILITY_ACTIVATION_STATE_CAPABILITY_KIND,
    CAPABILITY_ACTIVATION_STATE_CONNECTOR_ID,
    CAPABILITY_ACTIVATION_STATE_CONNECTOR_KIND,
    CAPABILITY_ACTIVATION_STATE_TABLE,
)
from umbod.core.configuration.persistence import TextCipher
from umbod.core.permissions.stores.schema import (
    CAPABILITY_PERMISSION_CONNECTOR_ID,
    CAPABILITY_PERMISSION_GROUP_ID,
    CAPABILITY_PERMISSION_KIND,
    CAPABILITY_PERMISSION_TABLE,
)
from umbod.core.persistence import AllOf, Database, DatabaseSession, Equals, OneOf, TransactionMode, UpsertCommand

from ..models import ToolCatalogSnapshot
from ..personal_connections.runtime_models import PersonalRuntimeAuthorizationQuery, PersonalRuntimeTarget, PersonalRuntimeUnavailable
from ..personal_tools import (
    AdmitPersonalTool,
    PersonalToolAdmission,
    PersonalToolObservation,
    PersonalToolPolicy,
    PersonalToolRecord,
    SavePersonalToolObservation,
    contract_fingerprint,
)
from .catalogs import find_catalog_record
from .personal_runtime_authorizations import load_personal_runtime_target
from .queries import query_all as _query
from .personal_tool_policies import load_personal_tool_policy
from .personal_tools_schema import (
    PERSONAL_TOOL_OBSERVATION_CONNECTOR_ID,
    PERSONAL_TOOL_OBSERVATION_NAMESPACE,
    PERSONAL_TOOL_OBSERVATION_SUBJECT,
    PERSONAL_TOOL_OBSERVATION_TABLE,
    PersonalToolObservationRecord,
    PersonalToolObservationRecordKey,
)
from .ports import CONNECTOR_DEFINITION_ADAPTER
from .schema import CONNECTOR_DEFINITION_CONNECTOR_ID, CONNECTOR_DEFINITION_TABLE, TOOL_CATALOG_TABLE


class EncryptedPersonalToolAccessStore:
    def __init__(self, database: Database, cipher: TextCipher) -> None:
        self._database = database
        self._cipher = cipher

    async def save_observation(self, command: SavePersonalToolObservation) -> None:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            target = await load_personal_runtime_target(session, self._cipher, command.query)
            policy = await load_personal_tool_policy(session, command.query.key.connector_id)
            if target != command.target or not isinstance(policy, PersonalToolPolicy) or policy.revision != command.contract_revision:
                raise PersonalRuntimeUnavailable("Personal discovery became stale")
            approved = {tool.identity.downstream_name: contract_fingerprint(tool) for tool in policy.tools}
            if (
                command.expires_at > target.expires_at
                or command.expires_at <= command.query.now
                or len({match.name for match in command.matches}) != len(command.matches)
                or any(approved.get(match.name) != match.fingerprint for match in command.matches)
            ):
                raise PersonalRuntimeUnavailable("Invalid personal observation")
            observation = PersonalToolObservation(key=target.key, authorization_revision=target.authorization_revision, configuration_revision=target.configuration_revision, contract_revision=policy.revision, matches=command.matches, expires_at=command.expires_at)
            key = PersonalToolObservationRecordKey(namespace=target.key.principal.namespace, subject=target.key.principal.subject, connector_id=target.key.connector_id)
            await session.upsert(PERSONAL_TOOL_OBSERVATION_TABLE, UpsertCommand(key=key, row=PersonalToolObservationRecord(**key.model_dump(), document=self._cipher.encrypt(observation.model_dump_json()))))

    async def list_available(self, query: PersonalRuntimeAuthorizationQuery) -> tuple[PersonalToolRecord, ...]:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            try:
                target = await load_personal_runtime_target(session, self._cipher, query)
                return await self._available(session, query, target)
            except Exception:
                return ()

    async def _available(self, session: DatabaseSession, query: PersonalRuntimeAuthorizationQuery, target: PersonalRuntimeTarget) -> tuple[PersonalToolRecord, ...]:
        policy = await load_personal_tool_policy(session, query.key.connector_id)
        if not isinstance(policy, PersonalToolPolicy):
            return ()
        row = await session.find_one(PERSONAL_TOOL_OBSERVATION_TABLE, _query(AllOf((Equals(PERSONAL_TOOL_OBSERVATION_CONNECTOR_ID, query.key.connector_id), Equals(PERSONAL_TOOL_OBSERVATION_NAMESPACE, query.key.principal.namespace), Equals(PERSONAL_TOOL_OBSERVATION_SUBJECT, query.key.principal.subject)))))
        if row is None:
            return ()
        observation = PersonalToolObservation.model_validate_json(self._cipher.decrypt(row.document))
        if (
            observation.key != query.key
            or observation.authorization_revision != target.authorization_revision
            or observation.configuration_revision != target.configuration_revision
            or observation.contract_revision != policy.revision
            or observation.expires_at <= query.now
            or observation.expires_at > target.expires_at
        ):
            return ()
        catalog = await find_catalog_record(session, TOOL_CATALOG_TABLE, query.key.connector_id)
        if catalog is None or ToolCatalogSnapshot.model_validate(catalog.snapshot).tools != policy.tools:
            return ()
        definition_row = await session.find_one(CONNECTOR_DEFINITION_TABLE, _query(Equals(CONNECTOR_DEFINITION_CONNECTOR_ID, query.key.connector_id)))
        if definition_row is None:
            return ()
        definition = CONNECTOR_DEFINITION_ADAPTER.validate_python(definition_row.document)
        observed = {match.name: match.fingerprint for match in observation.matches}
        activated = await self._activated_tools(session, query.key.connector_id)
        permitted = await self._permitted_tools(session, query)
        eligible = activated & permitted
        return tuple(
            PersonalToolRecord(definition=definition, tool=tool, contract_revision=policy.revision, fingerprint=contract_fingerprint(tool))
            for tool in policy.tools
            if tool.identity.downstream_name in eligible
            and observed.get(tool.identity.downstream_name) == contract_fingerprint(tool)
        )

    async def _activated_tools(self, session: DatabaseSession, connector_id: str) -> set[str]:
        rows = await session.find_many(CAPABILITY_ACTIVATION_STATE_TABLE, _query(AllOf((
            Equals(CAPABILITY_ACTIVATION_STATE_CONNECTOR_KIND, "downstream_mcp"),
            Equals(CAPABILITY_ACTIVATION_STATE_CONNECTOR_ID, connector_id),
            Equals(CAPABILITY_ACTIVATION_STATE_CAPABILITY_KIND, "tool"),
        ))))
        return {row.capability_key for row in rows if row.status == "enabled"}

    async def _permitted_tools(self, session: DatabaseSession, query: PersonalRuntimeAuthorizationQuery) -> set[str]:
        rows = await session.find_many(CAPABILITY_PERMISSION_TABLE, _query(AllOf((
            Equals(CAPABILITY_PERMISSION_CONNECTOR_ID, query.key.connector_id),
            Equals(CAPABILITY_PERMISSION_KIND, "tool"),
            OneOf(CAPABILITY_PERMISSION_GROUP_ID, query.group_ids),
        ))))
        return {row.capability_key for row in rows}

    async def admit(self, command: AdmitPersonalTool) -> PersonalToolAdmission:
        identity = command.identity
        if identity.connector_kind != "downstream_mcp" or identity.capability_kind != "tool" or identity.connector_id != command.query.key.connector_id:
            raise PersonalRuntimeUnavailable("Personal tool unavailable")
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            try:
                target = await load_personal_runtime_target(session, self._cipher, command.query)
                records = await self._available(session, command.query, target)
                for record in records:
                    if record.tool.identity.downstream_name == identity.capability_key and record.contract_revision == command.contract_revision and record.fingerprint == command.fingerprint:
                        return PersonalToolAdmission(target=target, tool=record.tool)
            except Exception:
                raise PersonalRuntimeUnavailable("Personal tool unavailable") from None
            raise PersonalRuntimeUnavailable("Personal tool unavailable")
