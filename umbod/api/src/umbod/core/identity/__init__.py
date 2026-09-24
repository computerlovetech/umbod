from collections.abc import Iterable
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class ConnectorIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)

    connector_id: str
    connector_type: str


class ConnectorIdentitySource(Protocol):
    async def identities(self) -> tuple[ConnectorIdentity, ...]: ...


class ConnectorIdentityConflictError(ValueError):
    def __init__(self, requested: ConnectorIdentity, existing: ConnectorIdentity) -> None:
        self.requested = requested
        self.existing = existing
        super().__init__(
            f"Connector ID '{requested.connector_id}' is already used by {existing.connector_type}"
        )


class AggregateConnectorIdentityCatalog:
    def __init__(self, sources: Iterable[ConnectorIdentitySource]) -> None:
        self._sources = tuple(sources)

    async def identities(self) -> tuple[ConnectorIdentity, ...]:
        identities: list[ConnectorIdentity] = []
        for source in self._sources:
            identities.extend(await source.identities())
        return tuple(identities)

    async def ensure_available(self, requested: ConnectorIdentity) -> None:
        for existing in await self.identities():
            if existing.connector_id == requested.connector_id:
                raise ConnectorIdentityConflictError(requested, existing)
