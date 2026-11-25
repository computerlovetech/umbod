from typing import Protocol

from .models import (
    PersonalOAuthConfiguration,
    PersonalOAuthConfigurationQuery,
    ReplacePersonalOAuthConfiguration,
)


class PersonalOAuthConfigurationStore(Protocol):
    async def delete_connector(self, connector_id: str) -> None: ...

    async def get(
        self, query: PersonalOAuthConfigurationQuery
    ) -> PersonalOAuthConfiguration: ...

    async def replace(
        self, command: ReplacePersonalOAuthConfiguration
    ) -> PersonalOAuthConfiguration: ...
