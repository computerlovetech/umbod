from collections.abc import Mapping
from dataclasses import dataclass

from umbod.core.connectors.downstream_mcp.catalog import DownstreamCapabilityRecord
from umbod.core.connectors.downstream_mcp.models import ConnectorDefinitionModel
from umbod.core.connectors.downstream_mcp.stores import ToolCatalogFound
from umbod.mcp.connectors.downstream_mcp.namespaces import PersonalToolNamespaceSnapshot


@dataclass(frozen=True)
class DownstreamDiscoverySnapshot:
    definitions: tuple[ConnectorDefinitionModel, ...]
    published_connector_ids: frozenset[str]
    records: tuple[DownstreamCapabilityRecord, ...]
    namespaces: Mapping[str, PersonalToolNamespaceSnapshot]
    published_records: tuple[DownstreamCapabilityRecord, ...]
    available_records: tuple[DownstreamCapabilityRecord, ...]
    catalogs: tuple[tuple[str, ToolCatalogFound], ...]
    descriptions: Mapping[str, str]


class DownstreamDiscoveryUnavailable(RuntimeError):
    pass
