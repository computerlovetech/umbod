from typing import Protocol

from .models import (
    ClaimedOAuthApplication,
    CompleteOAuthApplication,
    OAuthApplicationBinding,
    ReadyOAuthApplication,
    ResolveOAuthApplication,
)


class PersonalOAuthApplicationStore(Protocol):
    async def reserve(self, binding: OAuthApplicationBinding) -> ClaimedOAuthApplication | ReadyOAuthApplication: ...

    async def complete(self, command: CompleteOAuthApplication) -> ReadyOAuthApplication: ...

    async def resolve(self, query: ResolveOAuthApplication) -> ReadyOAuthApplication: ...
