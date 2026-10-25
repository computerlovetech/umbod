from typing import Protocol

from .models import (
    PersonalConnectionKey,
    PersonalConnectionState,
    ReplacePersonalAuthorization,
    SetPersonalConnectionEnabled,
)


class PersonalConnectionStore(Protocol):
    async def get(self, key: PersonalConnectionKey) -> PersonalConnectionState: ...

    async def set_enabled(
        self, command: SetPersonalConnectionEnabled
    ) -> PersonalConnectionState: ...

    async def disconnect(
        self, key: PersonalConnectionKey
    ) -> PersonalConnectionState: ...

    async def replace_authorization(
        self, command: ReplacePersonalAuthorization
    ) -> PersonalConnectionState: ...

    async def delete_connector(self, connector_id: str) -> None: ...
