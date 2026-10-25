from pydantic import SecretStr

from .models import (
    Authorized,
    PersonalConnectionKey,
    PersonalConnectionState,
    ReplacePersonalAuthorization,
    SetPersonalConnectionEnabled,
)
from .caller import PersonalCaller, UnavailablePersonalCaller, require_personal_caller
from .ports import PersonalConnectionStore


class PersonalConnectionService:
    def __init__(
        self, caller: PersonalCaller | UnavailablePersonalCaller, store: PersonalConnectionStore
    ) -> None:
        self._caller = caller
        self._store = store

    async def _key(self, connector_id: str) -> PersonalConnectionKey:
        principal = require_personal_caller(self._caller).principal
        return PersonalConnectionKey(principal=principal, connector_id=connector_id)

    async def get(self, connector_id: str) -> PersonalConnectionState:
        return await self._store.get(await self._key(connector_id))

    async def set_enabled(
        self, connector_id: str, enabled: bool
    ) -> PersonalConnectionState:
        return await self._store.set_enabled(
            SetPersonalConnectionEnabled(
                key=await self._key(connector_id), enabled=enabled
            )
        )

    async def disconnect(self, connector_id: str) -> PersonalConnectionState:
        return await self._store.disconnect(await self._key(connector_id))

    async def replace_authorization(
        self, connector_id: str, expected_revision: str, authorization: SecretStr
    ) -> PersonalConnectionState:
        return await self._store.replace_authorization(
            ReplacePersonalAuthorization(
                key=await self._key(connector_id),
                expected_revision=expected_revision,
                authorization=Authorized(authorization=authorization),
            )
        )
