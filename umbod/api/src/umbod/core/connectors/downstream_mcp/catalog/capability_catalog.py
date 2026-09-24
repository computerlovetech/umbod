from dataclasses import dataclass

from umbod.core.capabilities import (
    AbsentCapabilityOutputSchema,
    CapabilityIdentity,
    CapabilityKind,
    CapabilityNotFoundError,
    NormalizedCapability,
    PresentCapabilityOutputSchema,
)
from umbod.core.connectors.downstream_mcp.models import (
    ConnectorDefinitionModel,
    DiscoveredPrompt,
    DiscoveredResource,
    DiscoveredResourceTemplate,
    DiscoveredTool,
    DiscoveredToolWithOutputSchema,
)
from umbod.core.connectors.downstream_mcp.stores.ports import (
    ConnectorDefinitionFound,
    ConnectorDefinitionStore,
    ConnectorIdQuery,
    ToolCatalogFound,
    ToolCatalogStore,
)


@dataclass(frozen=True)
class DownstreamCapabilityRecord:
    definition: ConnectorDefinitionModel
    capability: NormalizedCapability
    source_tool: DiscoveredTool | None = None


class StoreBackedDownstreamCapabilityCatalog:
    def __init__(
        self, definitions: ConnectorDefinitionStore, catalogs: ToolCatalogStore
    ) -> None:
        self._definitions = definitions
        self._catalogs = catalogs

    async def list_capabilities(self) -> tuple[NormalizedCapability, ...]:
        return tuple(record.capability for record in await self.list_records())

    async def resolve(self, identity: CapabilityIdentity) -> NormalizedCapability:
        return (await self.resolve_record(identity)).capability

    async def list_records(self) -> tuple[DownstreamCapabilityRecord, ...]:
        records: list[DownstreamCapabilityRecord] = []
        for definition in (await self._definitions.list()).definitions:
            records.extend(await self._records_for(definition))
        return tuple(records)

    async def resolve_record(
        self, identity: CapabilityIdentity
    ) -> DownstreamCapabilityRecord:
        if identity.connector_kind != "downstream_mcp":
            raise CapabilityNotFoundError(identity)
        definition = await self._definitions.get(ConnectorIdQuery(connector_id=identity.connector_id))
        if not isinstance(definition, ConnectorDefinitionFound):
            raise CapabilityNotFoundError(identity)
        for record in await self._records_for(definition.definition):
            if record.capability.identity == identity:
                return record
        raise CapabilityNotFoundError(identity)

    async def has_connector(self, connector_id: str) -> bool:
        result = await self._catalogs.get(ConnectorIdQuery(connector_id=connector_id))
        return isinstance(result, ToolCatalogFound)

    async def _records_for(
        self, definition: ConnectorDefinitionModel
    ) -> tuple[DownstreamCapabilityRecord, ...]:
        result = await self._catalogs.get(ConnectorIdQuery(connector_id=definition.connector_id))
        if not isinstance(result, ToolCatalogFound):
            return ()
        records: list[DownstreamCapabilityRecord] = []
        for tool in result.snapshot.tools:
            records.append(
                DownstreamCapabilityRecord(
                    definition,
                    _normalize_tool(tool).model_copy(
                        update={"connector_display_name": definition.display_name}
                    ),
                    tool,
                )
            )
        for prompt in result.snapshot.prompts:
            records.append(
                DownstreamCapabilityRecord(
                    definition,
                    _normalize_prompt(definition.connector_id, prompt).model_copy(
                        update={"connector_display_name": definition.display_name}
                    ),
                )
            )
        for resource in result.snapshot.resources:
            records.append(
                DownstreamCapabilityRecord(
                    definition,
                    _normalize_resource(definition.connector_id, resource).model_copy(
                        update={"connector_display_name": definition.display_name}
                    ),
                )
            )
        for template in result.snapshot.resource_templates:
            records.append(
                DownstreamCapabilityRecord(
                    definition,
                    _normalize_resource_template(definition.connector_id, template).model_copy(
                        update={"connector_display_name": definition.display_name}
                    ),
                )
            )
        return tuple(records)


def _identity(
    connector_id: str, capability_kind: CapabilityKind, capability_key: str
) -> CapabilityIdentity:
    return CapabilityIdentity(
        connector_kind="downstream_mcp",
        connector_id=connector_id,
        capability_kind=capability_kind,
        capability_key=capability_key,
    )


def _normalize_tool(tool: DiscoveredTool) -> NormalizedCapability:
    output_schema = (
        PresentCapabilityOutputSchema(schema=tool.output_schema)
        if isinstance(tool, DiscoveredToolWithOutputSchema)
        else AbsentCapabilityOutputSchema()
    )
    return NormalizedCapability(
        identity=_identity(tool.identity.connector_id, "tool", tool.identity.downstream_name),
        title=tool.title,
        description=tool.description.strip() or tool.title,
        input_schema=tool.input_schema,
        output_schema=output_schema,
    )


def _normalize_prompt(connector_id: str, prompt: DiscoveredPrompt) -> NormalizedCapability:
    return NormalizedCapability(
        identity=_identity(connector_id, "prompt", prompt.name),
        title=prompt.title or prompt.name,
        description=(prompt.description or "").strip() or prompt.name,
        input_schema={"type": "object", "properties": {}},
        output_schema=AbsentCapabilityOutputSchema(),
    )


def _normalize_resource(connector_id: str, resource: DiscoveredResource) -> NormalizedCapability:
    return NormalizedCapability(
        identity=_identity(connector_id, "resource", resource.uri),
        title=resource.title or resource.name,
        description=(resource.description or "").strip() or resource.name,
        input_schema={"type": "object", "properties": {}},
        output_schema=AbsentCapabilityOutputSchema(),
    )


def _normalize_resource_template(
    connector_id: str, template: DiscoveredResourceTemplate
) -> NormalizedCapability:
    return NormalizedCapability(
        identity=_identity(connector_id, "resource_template", template.uri_template),
        title=template.title or template.name,
        description=(template.description or "").strip() or template.name,
        input_schema={"type": "object", "properties": {}},
        output_schema=AbsentCapabilityOutputSchema(),
    )
