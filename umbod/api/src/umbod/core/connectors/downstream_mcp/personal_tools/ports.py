from typing import Protocol

from ..personal_connections.runtime_models import PersonalRuntimeAuthorizationQuery, PersonalToolResult
from ..stores.ports import ConnectorIdQuery
from .models import (
    AdmitPersonalTool,
    InvokePersonalTool,
    PersonalRuntimeContext,
    PersonalToolAdmission,
    PersonalToolPolicy,
    PersonalToolPolicyReplacement,
    PersonalToolRecord,
    ReplacePersonalToolPolicy,
    SavePersonalToolObservation,
    UnconfiguredPersonalToolPolicy,
)


class PersonalRuntimeContextProvider(Protocol):
    async def get_context(self) -> PersonalRuntimeContext: ...


class PersonalToolRuntime(Protocol):
    async def list_tools(self) -> tuple[PersonalToolRecord, ...]: ...

    async def execute(self, command: InvokePersonalTool) -> PersonalToolResult: ...


class PersonalToolPolicyStore(Protocol):
    async def get(self, query: ConnectorIdQuery) -> PersonalToolPolicy | UnconfiguredPersonalToolPolicy: ...

    async def replace(self, command: ReplacePersonalToolPolicy) -> PersonalToolPolicyReplacement: ...

    async def delete_connector(self, connector_id: str) -> None: ...


class PersonalToolAccessStore(Protocol):
    async def list_available(self, query: PersonalRuntimeAuthorizationQuery) -> tuple[PersonalToolRecord, ...]: ...

    async def save_observation(self, command: SavePersonalToolObservation) -> None: ...

    async def admit(self, command: AdmitPersonalTool) -> PersonalToolAdmission: ...
