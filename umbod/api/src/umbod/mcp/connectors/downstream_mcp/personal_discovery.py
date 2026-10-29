import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import datetime
from types import MappingProxyType
from typing import Optional

from umbod.core.callers import AuthenticationProvenance
from umbod.core.connectors.downstream_mcp.models import uses_personal_oauth
from umbod.core.connectors.downstream_mcp.personal_connections.caller import PersonalCaller, PersonalCallerProvider, UnavailablePersonalCaller
from umbod.core.connectors.downstream_mcp.personal_tools.models import InvokePersonalTool, PersonalToolDiscoveryQuery, PersonalToolRecord
from umbod.core.connectors.downstream_mcp.personal_tools.ports import PersonalToolDiscoveryReader
from umbod.core.permissions import InMemoryGroupConnectorToolPermissions
from umbod.mcp.connectors.downstream_mcp.permissions import DownstreamToolPermissionPolicy, DownstreamToolPermissionPolicySource
from umbod.mcp.connectors.downstream_mcp.runtime import DownstreamDiscoveryRuntime, DownstreamDiscoverySnapshot


class PersonalDiscoveryOperation:
    def __init__(self, owner: "PersonalDiscoveryOperations", scope: str, snapshot: DownstreamDiscoverySnapshot, caller: PersonalCaller | UnavailablePersonalCaller, permission_policy: DownstreamToolPermissionPolicy) -> None:
        self.owner = owner
        self.scope = scope
        self.snapshot = snapshot
        self.caller = caller
        self.permission_policy = permission_policy
        self._load: Optional[asyncio.Task[tuple[PersonalToolRecord, ...]]] = None
        self._index: MappingProxyType[tuple[str, str, str, str], PersonalToolRecord] = MappingProxyType({})
        self.active = True

    def allows(self, connector_id: str) -> bool:
        if not self.active or not isinstance(self.caller, PersonalCaller):
            return False
        if self.caller.caller.authentication == AuthenticationProvenance.UNAVAILABLE:
            return False
        permissions = self.owner.permissions
        return connector_id in permissions.explicitly_granted_connector_ids(self.caller.groups)

    async def _read(self) -> tuple[PersonalToolRecord, ...]:
        if not isinstance(self.caller, PersonalCaller):
            return ()
        definitions = tuple(definition for definition in self.snapshot.definitions if uses_personal_oauth(definition) and definition.connector_id in self.snapshot.published_connector_ids and (not self.scope or definition.connector_id == self.scope) and self.allows(definition.connector_id))
        if not definitions:
            return ()
        records = await self.owner.reader.read(PersonalToolDiscoveryQuery(principal=self.caller.principal, definitions=definitions, now=self.owner.clock()))
        selected = {definition.connector_id: definition for definition in definitions}
        records = tuple(record for record in records if selected.get(record.definition.connector_id) == record.definition)
        self._index = MappingProxyType({self.record_key(record): record for record in records})
        return records

    @staticmethod
    def record_key(record: PersonalToolRecord) -> tuple[str, str, str, str]:
        return (record.definition.connector_id, record.tool.identity.downstream_name, record.inventory_revision, record.fingerprint)

    async def _loaded_records(self) -> tuple[PersonalToolRecord, ...]:
        if not self.active:
            return ()
        if self._load is None:
            self._load = asyncio.create_task(self._read())
        return await self._load

    async def records(self) -> tuple[PersonalToolRecord, ...]:
        return tuple(record for record in await self._loaded_records() if self.allows(record.definition.connector_id))

    async def contains(self, command: InvokePersonalTool) -> bool:
        await self._loaded_records()
        identity = command.identity
        return identity.connector_kind == "downstream_mcp" and identity.capability_kind == "tool" and self.allows(identity.connector_id) and (identity.connector_id, identity.capability_key, command.inventory_revision, command.fingerprint) in self._index

    async def close(self) -> None:
        self.active = False
        if self._load is not None and not self._load.done():
            self._load.cancel()
            try:
                await self._load
            except asyncio.CancelledError:
                pass
        self._load = None
        self._index = MappingProxyType({})
        self.caller = UnavailablePersonalCaller(kind="unavailable")


_OPERATION: ContextVar[Optional[PersonalDiscoveryOperation]] = ContextVar("personal_discovery_operation", default=None)


class PersonalDiscoveryOperations:
    def __init__(self, runtime: DownstreamDiscoveryRuntime, callers: PersonalCallerProvider, reader: PersonalToolDiscoveryReader, permissions: InMemoryGroupConnectorToolPermissions, clock: Callable[[], datetime], permission_policy: DownstreamToolPermissionPolicySource) -> None:
        self.runtime = runtime
        self.callers = callers
        self.reader = reader
        self.permissions = permissions
        self.clock = clock
        self.permission_policy = permission_policy

    @asynccontextmanager
    async def operation(self, scope: str) -> AsyncIterator[PersonalDiscoveryOperation]:
        current = _OPERATION.get()
        if current is not None and current.active and current.owner is self and current.scope == scope:
            yield current
            return
        permission_policy = self.permission_policy.capture()
        snapshot = self.runtime.capture()
        caller = await self.callers.get_caller()
        operation = PersonalDiscoveryOperation(self, scope, snapshot, caller, permission_policy)
        token = _OPERATION.set(operation)
        try:
            yield operation
        finally:
            _OPERATION.reset(token)
            await operation.close()

    async def is_authorized(self, command: InvokePersonalTool, scope: str) -> bool:
        async with self.operation(scope) as operation:
            return await operation.contains(command)
