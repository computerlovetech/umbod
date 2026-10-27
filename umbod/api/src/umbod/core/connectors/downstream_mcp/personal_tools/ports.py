from typing import Protocol

from umbod.core.connectors.downstream_mcp.personal_connections.health_models import RejectPersonalAuthorization

from ..personal_connections.runtime_models import PersonalRuntimeAuthorizationQuery, PersonalToolResult
from ..stores.ports import ConnectorDefinitionList, ConnectorIdQuery
from .models import (
    AdmitPersonalTool,
    InvokePersonalTool,
    PersonalInventoryRevision,
    PersonalToolAdmission,
    PersonalToolPolicy,
    PersonalToolPolicyReplacement,
    PersonalToolRecord,
    ReplacePersonalToolPolicy,
    SavePersonalToolObservation,
    UnconfiguredPersonalToolPolicy,
)


class PersonalToolDefinitionReader(Protocol):
    async def list(self) -> ConnectorDefinitionList: ...


class PersonalToolRuntime(Protocol):
    async def list_tools(self) -> tuple[PersonalToolRecord, ...]: ...

    async def execute(self, command: InvokePersonalTool) -> PersonalToolResult: ...


class PersonalToolPolicyStore(Protocol):
    async def get(self, query: ConnectorIdQuery) -> PersonalToolPolicy | UnconfiguredPersonalToolPolicy: ...

    async def replace(self, command: ReplacePersonalToolPolicy) -> PersonalToolPolicyReplacement: ...

    async def delete_connector(self, connector_id: str) -> None: ...


class PersonalToolAccessStore(Protocol):
    async def read_inventory_revision(self, query: PersonalRuntimeAuthorizationQuery) -> PersonalInventoryRevision: ...

    async def reject_authorization(self, command: RejectPersonalAuthorization) -> None: ...

    async def list_available(self, query: PersonalRuntimeAuthorizationQuery) -> tuple[PersonalToolRecord, ...]: ...

    async def save_observation(self, command: SavePersonalToolObservation) -> None: ...

    async def admit(self, command: AdmitPersonalTool) -> PersonalToolAdmission: ...
