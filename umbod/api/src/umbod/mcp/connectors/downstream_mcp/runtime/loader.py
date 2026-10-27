from dataclasses import dataclass
from types import MappingProxyType

from umbod.core.activation import ActivationStatus, ActivationStore, CapabilityRef
from umbod.core.capabilities.descriptions import ConnectorCapabilityDescriptionKey, ConnectorCapabilityDescriptionOverrideStore, OverriddenCapabilityDescription
from umbod.core.connectors.downstream_mcp.catalog import DownstreamCapabilityRecord, normalize_catalog
from umbod.core.connectors.downstream_mcp.models import uses_personal_oauth
from umbod.core.connectors.downstream_mcp.stores import ConnectorDefinitionStore, ConnectorIdQuery, CredentialFound, EncryptedCredentialStore, ToolCatalogFound, ToolCatalogStore
from umbod.core.publishing import ConnectorPublishingStore
from umbod.mcp.connectors.downstream_mcp.runtime.models import DownstreamDiscoverySnapshot
from umbod.mcp.connectors.downstream_mcp.namespaces import PersonalToolNamespaceSnapshot


@dataclass(frozen=True)
class DownstreamDiscoveryStores:
    definitions: ConnectorDefinitionStore
    credentials: EncryptedCredentialStore
    catalogs: ToolCatalogStore
    publishing: ConnectorPublishingStore
    activations: ActivationStore
    descriptions: ConnectorCapabilityDescriptionOverrideStore


class StoreBackedDownstreamDiscoveryLoader:
    def __init__(self, stores: DownstreamDiscoveryStores) -> None:
        self._stores = stores

    async def load(self) -> DownstreamDiscoverySnapshot:
        definitions = (await self._stores.definitions.list()).definitions
        keys = tuple(ConnectorCapabilityDescriptionKey(kind="downstream_mcp", connector_id=item.connector_id) for item in definitions)
        states = await self._stores.descriptions.get_many(keys)
        descriptions = MappingProxyType({definition.connector_id: state.description if isinstance(state, OverriddenCapabilityDescription) else definition.capability_description for definition, state in zip(definitions, states, strict=True)})
        published_ids = frozenset([definition.connector_id for definition in definitions if await self._stores.publishing.is_published(definition.connector_id)])
        namespaces = MappingProxyType({scope: PersonalToolNamespaceSnapshot(definitions, scope) for scope in ("", *(definition.connector_id for definition in definitions))})
        all_records: list[DownstreamCapabilityRecord] = []
        published: list[DownstreamCapabilityRecord] = []
        available: list[DownstreamCapabilityRecord] = []
        catalogs: list[tuple[str, ToolCatalogFound]] = []
        for definition in definitions:
            if uses_personal_oauth(definition):
                continue
            connector_id = definition.connector_id
            query = ConnectorIdQuery(connector_id=connector_id)
            catalog = await self._stores.catalogs.get(query)
            if not isinstance(catalog, ToolCatalogFound):
                continue
            records = normalize_catalog(definition, catalog.snapshot)
            all_records.extend(records)
            if connector_id not in published_ids:
                continue
            published.extend(records)
            credential = await self._stores.credentials.get(query)
            if not isinstance(credential, CredentialFound):
                continue
            catalogs.append((connector_id, catalog))
            for record in records:
                identity = record.capability.identity
                ref = CapabilityRef(connector_kind="downstream_mcp", connector_id=connector_id, capability_kind=identity.capability_kind, capability_key=identity.capability_key)
                if await self._stores.activations.get_status(ref) == ActivationStatus.ENABLED:
                    available.append(record)
        return DownstreamDiscoverySnapshot(definitions=definitions, published_connector_ids=published_ids, records=tuple(all_records), namespaces=namespaces, published_records=tuple(published), available_records=tuple(available), catalogs=tuple(catalogs), descriptions=descriptions)
