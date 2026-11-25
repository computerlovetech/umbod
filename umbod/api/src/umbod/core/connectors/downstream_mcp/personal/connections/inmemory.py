import asyncio

from .models import (
    MissingPersonalConnection,
    PersonalConnection,
    PersonalConnectionKey,
    PersonalConnectionState,
    ReplacePersonalAuthorization,
    SetPersonalConnectionEnabled,
    disconnected,
    replace_authorization,
    set_enabled,
)


class InMemoryPersonalConnectionStore:
    def __init__(self) -> None:
        self._records: dict[PersonalConnectionKey, PersonalConnection] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: PersonalConnectionKey) -> PersonalConnectionState:
        return self._records.get(key, MissingPersonalConnection(key=key))

    def _save(self, state: PersonalConnectionState) -> PersonalConnectionState:
        if isinstance(state, PersonalConnection):
            self._records[state.key] = state
        return state

    async def set_enabled(
        self, command: SetPersonalConnectionEnabled
    ) -> PersonalConnectionState:
        async with self._lock:
            return self._save(set_enabled(await self.get(command.key), command.enabled))

    async def disconnect(self, key: PersonalConnectionKey) -> PersonalConnectionState:
        async with self._lock:
            return self._save(disconnected(await self.get(key)))

    async def replace_authorization(
        self, command: ReplacePersonalAuthorization
    ) -> PersonalConnectionState:
        async with self._lock:
            return self._save(
                replace_authorization(await self.get(command.key), command)
            )

    async def delete_connector(self, connector_id: str) -> None:
        async with self._lock:
            self._records = {
                key: value
                for key, value in self._records.items()
                if key.connector_id != connector_id
            }
