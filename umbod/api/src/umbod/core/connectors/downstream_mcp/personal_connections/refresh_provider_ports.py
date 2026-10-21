from typing import Protocol

from .models import Authorized
from .refresh_provider_models import RefreshPersonalOAuth


class PersonalOAuthRefreshProvider(Protocol):
    async def refresh(self, command: RefreshPersonalOAuth) -> Authorized: ...
