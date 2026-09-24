from typing import Protocol

from umbod.core.capabilities.domain import (
    CapabilityIdentity,
    NormalizedCapability,
)


class CapabilityCatalog(Protocol):
    async def list_capabilities(self) -> tuple[NormalizedCapability, ...]: ...

    async def resolve(self, identity: CapabilityIdentity) -> NormalizedCapability: ...


class CapabilityNotFoundError(LookupError):
    def __init__(self, identity: CapabilityIdentity) -> None:
        self.identity = identity
        super().__init__(
            f"Capability '{identity.connector_id}/{identity.capability_key}' was not found"
        )


class CapabilityIdentityConflictError(ValueError):
    def __init__(self, identity: CapabilityIdentity) -> None:
        self.identity = identity
        super().__init__(
            f"Capability '{identity.connector_id}/{identity.capability_key}' is ambiguous"
        )


class InMemoryCapabilityCatalog:
    def __init__(self, capabilities: tuple[NormalizedCapability, ...]) -> None:
        self._capabilities = capabilities
        self._by_identity = {capability.identity: capability for capability in capabilities}
        if len(self._by_identity) != len(capabilities):
            raise CapabilityIdentityConflictError(_first_duplicate_identity(capabilities))

    async def list_capabilities(self) -> tuple[NormalizedCapability, ...]:
        return self._capabilities

    async def resolve(self, identity: CapabilityIdentity) -> NormalizedCapability:
        try:
            return self._by_identity[identity]
        except KeyError as error:
            raise CapabilityNotFoundError(identity) from error


def _first_duplicate_identity(
    capabilities: tuple[NormalizedCapability, ...],
) -> CapabilityIdentity:
    identities: set[CapabilityIdentity] = set()
    for capability in capabilities:
        if capability.identity in identities:
            return capability.identity
        identities.add(capability.identity)
    raise ValueError("Capabilities do not contain duplicate identities")
