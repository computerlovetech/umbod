from typing import Protocol

from .inventory_models import (
    PersonalConnectorQuery,
    PersonalConnectorSelection,
    PersonalConnectorSelections,
    SetPersonalConnectorEnablement,
)


class PersonalConnectorInventory(Protocol):
    async def list(self) -> PersonalConnectorSelections: ...

    async def get(self, query: PersonalConnectorQuery) -> PersonalConnectorSelection: ...

    async def set_enabled(
        self, command: SetPersonalConnectorEnablement
    ) -> PersonalConnectorSelection: ...

    async def disconnect(self, query: PersonalConnectorQuery) -> None: ...
