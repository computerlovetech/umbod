import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from umbod.core.configuration.persistence import TextCipher
from umbod.core.connectors.downstream_mcp.models import ConnectorDefinition, uses_personal_oauth
from umbod.core.connectors.downstream_mcp.personal.oauth.configuration import PersonalOAuthConfigurationUnavailable
from umbod.core.connectors.downstream_mcp.personal.oauth.setup import (
    CompletePersonalOAuthSetup,
    PersonalOAuthSetupBinding,
    PersonalOAuthSetupConflict,
    PersonalOAuthSetupQuery,
    PersonalOAuthSetupReceipt,
    PersonalOAuthSetupRequired,
    PersonalOAuthSetupStatus,
    SetupInProgress,
    SetupRequired,
    SetupValidated,
    StartPersonalOAuthSetup,
    StartedPersonalOAuthSetup,
)
from umbod.core.persistence import AllFields, Database, DatabaseSession, Equals, Query, TransactionMode, Unordered, UpsertCommand
from .personal_oauth_configurations import load_personal_oauth_configuration
from .personal_oauth_setup_schema import PERSONAL_OAUTH_SETUP_CONNECTOR_ID, PERSONAL_OAUTH_SETUP_TABLE, PersonalOAuthSetupKey, PersonalOAuthSetupRecord
from .ports import CONNECTOR_DEFINITION_ADAPTER
from .schema import CONNECTOR_DEFINITION_CONNECTOR_ID, CONNECTOR_DEFINITION_TABLE


def definition_fingerprint(definition: ConnectorDefinition) -> str:
    return hashlib.sha256(definition.model_dump_json().encode()).hexdigest()


async def load_setup_receipt(session: DatabaseSession, connector_id: str) -> PersonalOAuthSetupReceipt | None:
    row = await session.find_one(PERSONAL_OAUTH_SETUP_TABLE, Query(filter=Equals(PERSONAL_OAUTH_SETUP_CONNECTOR_ID, connector_id), projection=AllFields(), ordering=Unordered()))
    if row is None:
        return None
    receipt = PersonalOAuthSetupReceipt.model_validate_json(row.document)
    if receipt.binding.connector_id != connector_id:
        raise PersonalOAuthConfigurationUnavailable("Personal OAuth setup unavailable")
    return receipt


async def require_current_setup(session: DatabaseSession, definition: ConnectorDefinition, policy_revision: str, redirect_uri: str) -> None:
    receipt = await load_setup_receipt(session, definition.connector_id)
    binding = PersonalOAuthSetupBinding(connector_id=definition.connector_id, redirect_uri=redirect_uri, policy_revision=policy_revision, definition_fingerprint=definition_fingerprint(definition))
    if receipt is None or receipt.binding != binding or not isinstance(receipt.state, SetupValidated):
        raise PersonalOAuthSetupRequired("Personal OAuth setup validation required")


async def _save(session: DatabaseSession, receipt: PersonalOAuthSetupReceipt) -> None:
    await session.upsert(PERSONAL_OAUTH_SETUP_TABLE, UpsertCommand(key=PersonalOAuthSetupKey(connector_id=receipt.binding.connector_id), row=PersonalOAuthSetupRecord(connector_id=receipt.binding.connector_id, document=receipt.model_dump_json())))


def _status(receipt: PersonalOAuthSetupReceipt, now: datetime) -> PersonalOAuthSetupStatus:
    state = receipt.state
    if isinstance(state, SetupInProgress) and state.lease_expires_at <= now:
        state = SetupRequired()
    return PersonalOAuthSetupStatus(connector_id=receipt.binding.connector_id, revision=receipt.revision, policy_revision=receipt.binding.policy_revision, redirect_uri=receipt.binding.redirect_uri, state=state)


class PersonalOAuthSetupStoreService:
    def __init__(self, database: Database, cipher: TextCipher, clock: Callable[[], datetime]) -> None:
        self._database = database
        self._cipher = cipher
        self._clock = clock

    async def _current(self, session: DatabaseSession, query: PersonalOAuthSetupQuery) -> StartedPersonalOAuthSetup:
        row = await session.find_one(CONNECTOR_DEFINITION_TABLE, Query(filter=Equals(CONNECTOR_DEFINITION_CONNECTOR_ID, query.connector_id), projection=AllFields(), ordering=Unordered()))
        if row is None:
            raise PersonalOAuthConfigurationUnavailable("Personal OAuth setup unavailable")
        definition = CONNECTOR_DEFINITION_ADAPTER.validate_python(row.document)
        if not uses_personal_oauth(definition):
            raise PersonalOAuthConfigurationUnavailable("Personal OAuth setup unavailable")
        configuration = await load_personal_oauth_configuration(session, self._cipher, query.connector_id)
        binding = PersonalOAuthSetupBinding(connector_id=query.connector_id, redirect_uri=query.redirect_uri, policy_revision=configuration.policy.revision, definition_fingerprint=definition_fingerprint(definition))
        receipt = await load_setup_receipt(session, query.connector_id)
        if receipt is None or receipt.binding != binding:
            revision = hashlib.sha256(binding.model_dump_json().encode()).hexdigest()
            receipt = PersonalOAuthSetupReceipt(binding=binding, revision=revision, state=SetupRequired())
        return StartedPersonalOAuthSetup(receipt=receipt, endpoint_url=definition.endpoint_url, policy=configuration.policy)

    async def require_current(self, binding: PersonalOAuthSetupBinding) -> None:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            receipt = await load_setup_receipt(session, binding.connector_id)
            if receipt is None or receipt.binding != binding or not isinstance(receipt.state, SetupValidated):
                raise PersonalOAuthSetupRequired("Personal OAuth setup validation required")

    async def get(self, query: PersonalOAuthSetupQuery) -> PersonalOAuthSetupStatus:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            current = await self._current(session, query)
            return _status(current.receipt, self._clock())

    async def start(self, command: StartPersonalOAuthSetup) -> StartedPersonalOAuthSetup:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            current = await self._current(session, command)
            now = self._clock()
            state = current.receipt.state
            if current.receipt.revision != command.expected_revision or (isinstance(state, SetupInProgress) and state.lease_expires_at > now):
                raise PersonalOAuthSetupConflict("Personal OAuth setup revision conflict")
            receipt = PersonalOAuthSetupReceipt(binding=current.receipt.binding, revision=uuid4().hex, state=SetupInProgress(operation=command.operation, attempt_id=uuid4().hex, lease_expires_at=now + timedelta(seconds=90)))
            await _save(session, receipt)
            return StartedPersonalOAuthSetup(receipt=receipt, endpoint_url=current.endpoint_url, policy=current.policy)

    async def complete(self, command: CompletePersonalOAuthSetup) -> PersonalOAuthSetupStatus:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            started = command.started
            current = await self._current(session, started.receipt.binding)
            state = current.receipt.state
            if current.receipt != started.receipt or not isinstance(state, SetupInProgress) or state.lease_expires_at <= self._clock():
                raise PersonalOAuthSetupConflict("Personal OAuth setup result is stale")
            receipt = PersonalOAuthSetupReceipt(binding=current.receipt.binding, revision=uuid4().hex, state=command.state)
            await _save(session, receipt)
            return _status(receipt, self._clock())


def setup_clock() -> datetime:
    return datetime.now(UTC)
