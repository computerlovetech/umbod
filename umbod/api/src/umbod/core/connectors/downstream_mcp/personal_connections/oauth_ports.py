from typing import Protocol

from .models import Authorized
from .oauth_models import (
    ClaimPersonalOAuthAttempt,
    ClaimedPersonalOAuthAttempt,
    CompletePersonalOAuthAttempt,
    ExchangePersonalOAuth,
    FailPersonalOAuthAttempt,
    PersonalOAuthAttemptQuery,
    PersonalOAuthAttemptView,
    PreparePersonalOAuth,
    PreparedPersonalOAuth,
    PublishPersonalOAuthAttempt,
    ReservePersonalOAuthAttempt,
)


class PersonalOAuthProvider(Protocol):
    async def prepare(self, command: PreparePersonalOAuth) -> PreparedPersonalOAuth: ...

    async def exchange(self, command: ExchangePersonalOAuth) -> Authorized: ...


class PersonalOAuthAttemptStore(Protocol):
    async def reserve(self, command: ReservePersonalOAuthAttempt) -> PersonalOAuthAttemptView: ...

    async def publish(self, command: PublishPersonalOAuthAttempt) -> PersonalOAuthAttemptView: ...

    async def get(self, query: PersonalOAuthAttemptQuery) -> PersonalOAuthAttemptView: ...

    async def cancel(self, query: PersonalOAuthAttemptQuery) -> PersonalOAuthAttemptView: ...

    async def abort_preparation(self, query: PersonalOAuthAttemptQuery) -> None: ...

    async def claim(self, command: ClaimPersonalOAuthAttempt) -> ClaimedPersonalOAuthAttempt: ...

    async def complete(self, command: CompletePersonalOAuthAttempt) -> PersonalOAuthAttemptView: ...

    async def fail(self, command: FailPersonalOAuthAttempt) -> None: ...

    async def delete_connector(self, connector_id: str) -> None: ...
