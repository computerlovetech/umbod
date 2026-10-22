from collections import Counter

from umbod.core.connectors.downstream_mcp.user_catalogue import PersonalNamespace
from umbod.core.user_catalogue import CatalogueConnector, CatalogueSource

CapabilityNameKey = tuple[str, str, str, str]


class CollisionSafeSource:
    def __init__(
        self, source: CatalogueSource, names: dict[CapabilityNameKey, str],
        namespace: PersonalNamespace, blocked: frozenset[CapabilityNameKey],
    ) -> None:
        self._source = source
        self._names = names
        self._namespace = namespace
        self._blocked = blocked

    async def list_connectors(self) -> tuple[CatalogueConnector, ...]:
        connectors: list[CatalogueConnector] = []
        for connector in await self._source.list_connectors():
            capabilities = tuple(
                capability for capability in connector.capabilities
                if self._allows(connector, capability.kind, capability.key)
            )
            if capabilities or connector.ownership == "personal":
                connectors.append(connector.model_copy(update={"capabilities": capabilities}))
        return tuple(connectors)

    def _allows(self, connector: CatalogueConnector, kind: str, key: str) -> bool:
        identity = (connector.kind, connector.connector_id, kind, key)
        if identity in self._blocked:
            return False
        if kind != "tool":
            return True
        name = self._names.get(identity, "")
        return bool(name) and self._namespace.allows(
            name, connector.connector_id, connector.ownership == "personal",
        )


def gateway_tools_unavailable(
    names: dict[CapabilityNameKey, str], namespace: PersonalNamespace,
    personal_ids: frozenset[str],
) -> bool:
    configured = {
        identity: name for identity, name in names.items()
        if identity[0] in ("native", "downstream_mcp") and identity[2] == "tool"
    }
    return bool(duplicate_names(configured)) or any(
        not namespace.allows(name, identity[1], identity[1] in personal_ids)
        for identity, name in configured.items()
    )


def duplicate_names(names: dict[CapabilityNameKey, str]) -> frozenset[CapabilityNameKey]:
    counts = Counter(
        ("resource" if key[2] == "resource_template" else key[2], name)
        for key, name in names.items()
    )
    return frozenset(
        key for key, name in names.items()
        if counts[("resource" if key[2] == "resource_template" else key[2], name)] > 1
    )
