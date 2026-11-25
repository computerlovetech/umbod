from typing import Protocol

from ...connections import Authorized
from .provider_models import RefreshPersonalOAuth


class PersonalOAuthRefreshProvider(Protocol):
    async def refresh(self, command: RefreshPersonalOAuth) -> Authorized: ...
