from .models import CatalogueConnector, UserCatalogue
from .ports import CatalogueSource


class UserCatalogueService:
    def __init__(
        self, sources: tuple[CatalogueSource, ...], personal_enabled: bool, identity_key: str,
    ) -> None:
        self._sources = sources
        self._personal_enabled = personal_enabled
        self._identity_key = identity_key

    async def read(self) -> UserCatalogue:
        connectors: list[CatalogueConnector] = []
        for source in self._sources:
            connectors.extend(await source.list_connectors())
        return UserCatalogue(
            identity_key=self._identity_key,
            personal_enabled=self._personal_enabled,
            connectors=tuple(sorted(connectors, key=lambda item: (item.kind, item.connector_id, item.ownership))),
        )
