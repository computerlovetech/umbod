from .models import CatalogueConnector


class InMemoryCatalogueSource:
    def __init__(self, connectors: tuple[CatalogueConnector, ...]) -> None:
        self._connectors = connectors

    async def list_connectors(self) -> tuple[CatalogueConnector, ...]:
        return self._connectors
