from typing import Any

from umbod_desktop.backward_compatibility.contracts import (
    LegacyAuthorization,
    PrefixUpdate,
)
from umbod_desktop.contracts import (
    AdministrationRejected,
    ConnectorBinding,
    ConnectorCreation,
    ConnectorDefinition,
    PreparedUpstream,
    ProxyConfiguration,
    ToolGrant,
    ToolSelection,
    UpstreamInput,
)


class MemoryState:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.saves = 0

    def save(self) -> None:
        self.saves += 1


class MemoryAdministration:
    def __init__(self, definitions: tuple[ConnectorDefinition, ...]) -> None:
        self.definitions = {item.connector_id: item for item in definitions}
        self.patches: list[tuple[str, dict[str, str]]] = []
        self.rejected: set[str] = set()
        self.created: list[ConnectorCreation] = []
        self.discovered: list[str] = []
        self.names: tuple[str, ...] = ("read", "write")
        self.enabled: list[ToolSelection] = []
        self.grants: list[ToolGrant] = []
        self.groups: list[str] = []
        self.published: list[str] = []

    async def inventory(self) -> tuple[ConnectorDefinition, ...]:
        return tuple(self.definitions.values())

    async def create(self, command: ConnectorCreation) -> ConnectorDefinition:
        self.created.append(command)
        definition = ConnectorDefinition(
            connector_id=f"connector-{len(self.created)}",
            display_name=command.display_name,
            tool_name_prefix=command.tool_name_prefix,
            public_path=command.public_path,
        )
        self.definitions[definition.connector_id] = definition
        return definition

    async def discover(self, connector_id: str) -> None:
        self.discovered.append(connector_id)

    async def tool_names(self, connector_id: str) -> tuple[str, ...]:
        return self.names

    async def enable_tools(self, selection: ToolSelection) -> None:
        self.enabled.append(selection)

    async def ensure_group(self, group_id: str) -> None:
        self.groups.append(group_id)

    async def grant_tools(self, grant: ToolGrant) -> None:
        self.grants.append(grant)

    async def publish(self, connector_id: str) -> None:
        self.published.append(connector_id)

    async def update_prefix(self, update: PrefixUpdate) -> None:
        self.patches.append((update.connector_id, {"tool_name_prefix": update.prefix}))
        if update.connector_id in self.rejected:
            raise AdministrationRejected()
        self.definitions[update.connector_id] = self.definitions[update.connector_id].model_copy(
            update={"tool_name_prefix": update.prefix}
        )


class MemoryNamingPolicy:
    def readable_prefix(self, display_name: str) -> str:
        return {"Finance API": "Finance_API"}.get(display_name, display_name)

    def collision_key(self, prefix: str) -> str:
        return {"Finance-API": "Finance_API"}.get(prefix, prefix)


class MemoryUpstreams:
    def __init__(self) -> None:
        self.prepared: list[UpstreamInput] = []
        self.bindings: list[ConnectorBinding] = []

    async def prepare(self, server: UpstreamInput) -> PreparedUpstream:
        self.prepared.append(server)
        return PreparedUpstream(
            host_id="host", connection_changed=True,
            configuration=self.proxy_configuration("host"),
        )

    def proxy_configuration(self, host_id: str) -> ProxyConfiguration:
        return ProxyConfiguration(
            auth_mode="static_bearer", endpoint_url=f"http://127.0.0.1/{host_id}",
            header_type="bearer", bearer_token="private-loopback-token",
        )

    def bind(self, binding: ConnectorBinding) -> None:
        self.bindings.append(binding)


class MemoryAuthorizationImporter:
    def __init__(self) -> None:
        self.imported: list[LegacyAuthorization] = []

    def import_authorization(self, authorization: LegacyAuthorization) -> None:
        self.imported.append(authorization)
