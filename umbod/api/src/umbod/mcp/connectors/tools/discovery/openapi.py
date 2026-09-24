from typing import Optional, Protocol

from pydantic import BaseModel, ConfigDict

from umbod.core.capabilities import (
    CapabilityCatalog,
    NormalizedCapability,
)
from umbod.mcp.connectors.tools.discovery.search import ConnectorToolSearchCandidate


class OpenApiConnectorDiscoveryResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidates: tuple[ConnectorToolSearchCandidate, ...]


class OpenApiConnectorDiscovery(Protocol):
    async def enumerate(self) -> OpenApiConnectorDiscoveryResult: ...

    async def search(self, query: str) -> OpenApiConnectorDiscoveryResult: ...


class NormalizedOpenApiConnectorDiscovery:
    def __init__(self, catalog: CapabilityCatalog) -> None:
        self._catalog = catalog

    async def enumerate(self) -> OpenApiConnectorDiscoveryResult:
        capabilities = await self._catalog.list_capabilities()
        return OpenApiConnectorDiscoveryResult(
            candidates=tuple(_candidate(capability) for capability in capabilities)
        )

    async def search(self, query: str) -> OpenApiConnectorDiscoveryResult:
        capabilities = _lexical_search(query, await self._catalog.list_capabilities())
        return OpenApiConnectorDiscoveryResult(
            candidates=tuple(_candidate(capability) for capability in capabilities[:50])
        )


def _candidate(capability: NormalizedCapability) -> ConnectorToolSearchCandidate:
    identity = capability.identity
    searchable_details = " ".join(
        (
            capability.connector_display_name,
            capability.title,
            capability.description,
            *capability.search_hints,
        )
    )
    return ConnectorToolSearchCandidate(
        tool_name="execute_openapi",
        description=(
            f"OpenAPI operation {identity.capability_key}: {searchable_details}"
        ).strip(),
        connector_id=identity.connector_id,
        connector_display_name=capability.connector_display_name,
        connector_capability_description=capability.connector_capability_description,
        operation_name=identity.capability_key,
        input_schema=capability.input_schema,
        search_hints=capability.search_hints,
    )


def _lexical_search(
    query: str, capabilities: tuple[NormalizedCapability, ...]
) -> tuple[NormalizedCapability, ...]:
    normalized_query = query.strip().casefold()
    stable = sorted(capabilities, key=_stable_key)
    if not normalized_query:
        return tuple(stable)
    ranked = [
        (score, capability)
        for capability in stable
        if (score := _match_score(normalized_query, capability)) is not None
    ]
    ranked.sort(key=lambda item: (item[0], _stable_key(item[1])))
    return tuple(capability for _, capability in ranked)


def _match_score(query: str, capability: NormalizedCapability) -> Optional[int]:
    operation_name = capability.identity.capability_key.casefold()
    if operation_name == query:
        return 0
    if operation_name.startswith(query):
        return 1
    if query in operation_name:
        return 2
    fields = (capability.title, *capability.search_hints, capability.description)
    for index, value in enumerate(fields, start=3):
        if query in value.casefold():
            return index
    return None


def _stable_key(capability: NormalizedCapability) -> tuple[str, str, str]:
    return (
        capability.connector_display_name.casefold(),
        capability.identity.connector_id,
        capability.identity.capability_key,
    )
