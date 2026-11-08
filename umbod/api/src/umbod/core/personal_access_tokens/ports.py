from datetime import datetime
from typing import Optional, Protocol, TypedDict

from umbod.core.callers import CallerContext

from .models import (
    GeneratedPersonalAccessToken,
    PersonalAccessTokenMetadata,
    StoredPersonalAccessToken,
    TokenOwner,
)


class PersonalAccessTokenOwnerResolver(Protocol):
    def resolve(self, caller: CallerContext) -> TokenOwner: ...


class PersonalAccessTokenOwnerOptions(TypedDict, total=False):
    owner_resolver: PersonalAccessTokenOwnerResolver


class PersonalAccessTokenStore(Protocol):
    async def insert(self, record: StoredPersonalAccessToken) -> bool: ...

    async def find(self, token_id: str) -> Optional[StoredPersonalAccessToken]: ...

    async def list_tokens(
        self, owner: TokenOwner
    ) -> tuple[PersonalAccessTokenMetadata, ...]: ...

    async def revoke(self, owner: TokenOwner, token_id: str) -> bool: ...


class PersonalAccessTokenClock(Protocol):
    def now(self) -> datetime: ...


class PersonalAccessTokenGenerator(Protocol):
    def generate(self) -> GeneratedPersonalAccessToken: ...
