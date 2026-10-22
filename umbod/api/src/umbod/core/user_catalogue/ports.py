from typing import Protocol

from .models import CatalogueConnector, UserCatalogue


class CatalogueSource(Protocol):
    async def list_connectors(self) -> tuple[CatalogueConnector, ...]: ...


class UserCatalogueReader(Protocol):
    async def read(self) -> UserCatalogue: ...
