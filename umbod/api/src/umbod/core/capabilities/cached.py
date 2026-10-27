from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping
from uuid import UUID, uuid4

from umbod.core.caching import AsyncRequestCache
from umbod.core.capabilities.catalog import (
    CapabilityCatalog,
    CapabilityIdentityConflictError,
    CapabilityNotFoundError,
)
from umbod.core.capabilities.domain import CapabilityIdentity, NormalizedCapability


@dataclass(frozen=True)
class CapabilityCatalogSnapshot:
    capabilities: tuple[NormalizedCapability, ...]
    by_identity: Mapping[CapabilityIdentity, NormalizedCapability]


class CachedCapabilityCatalog(CapabilityCatalog):
    def __init__(
        self,
        catalog: CapabilityCatalog,
        cache: AsyncRequestCache[UUID, CapabilityCatalogSnapshot],
    ) -> None:
        self._catalog = catalog
        self._cache = cache
        self._key = uuid4()

    async def _load_snapshot(self) -> CapabilityCatalogSnapshot:
        capabilities = tuple(
            capability.model_copy(deep=True)
            for capability in await self._catalog.list_capabilities()
        )
        by_identity: dict[CapabilityIdentity, NormalizedCapability] = {}
        for capability in capabilities:
            if capability.identity in by_identity:
                raise CapabilityIdentityConflictError(capability.identity)
            by_identity[capability.identity] = capability
        return CapabilityCatalogSnapshot(capabilities, MappingProxyType(by_identity))

    async def list_capabilities(self) -> tuple[NormalizedCapability, ...]:
        snapshot = await self._cache.get_or_load(self._key, self._load_snapshot)
        return tuple(capability.model_copy(deep=True) for capability in snapshot.capabilities)

    async def resolve(self, identity: CapabilityIdentity) -> NormalizedCapability:
        snapshot = await self._cache.get_or_load(self._key, self._load_snapshot)
        try:
            capability = snapshot.by_identity[identity]
        except KeyError as error:
            raise CapabilityNotFoundError(identity) from error
        return capability.model_copy(deep=True)
