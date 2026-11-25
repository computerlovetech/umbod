from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from umbod.core.connectors.downstream_mcp.personal.connections import RejectPersonalAuthorization

from .runtime_models import PersonalRuntimeAuthorizationQuery, PersonalToolResult
from .models import (
    AdmitPersonalTool,
    InvokePersonalTool,
    PersonalInventoryRevision,
    PersonalToolAdmission,
    PersonalToolDiscoveryQuery,
    PersonalToolPolicy,
    PersonalToolPolicyReplacement,
    PersonalToolRecord,
    ReplacePersonalToolPolicy,
    SavePersonalToolObservation,
    UnconfiguredPersonalToolPolicy,
)


if TYPE_CHECKING:
    from ...stores.ports import ConnectorIdQuery


class PersonalToolDiscoveryReader(Protocol):
    async def read(self, query: PersonalToolDiscoveryQuery) -> tuple[PersonalToolRecord, ...]: ...

    async def read_available(self, query: PersonalToolDiscoveryQuery) -> tuple[PersonalToolRecord, ...]: ...


class PersonalToolRuntime(Protocol):
    async def execute(self, command: InvokePersonalTool) -> PersonalToolResult: ...


class PersonalToolPolicyStore(Protocol):
    async def get(self, query: ConnectorIdQuery) -> PersonalToolPolicy | UnconfiguredPersonalToolPolicy: ...

    async def replace(self, command: ReplacePersonalToolPolicy) -> PersonalToolPolicyReplacement: ...

    async def delete_connector(self, connector_id: str) -> None: ...


class PersonalToolAccessStore(Protocol):
    async def read_inventory_revision(self, query: PersonalRuntimeAuthorizationQuery) -> PersonalInventoryRevision: ...

    async def reject_authorization(self, command: RejectPersonalAuthorization) -> None: ...

    async def save_observation(self, command: SavePersonalToolObservation) -> None: ...

    async def admit(self, command: AdmitPersonalTool) -> PersonalToolAdmission: ...
