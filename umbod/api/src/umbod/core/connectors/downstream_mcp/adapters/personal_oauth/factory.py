from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from ...personal_connections.oauth_ports import PersonalOAuthProvider
from ...personal_connections.refresh_provider_ports import PersonalOAuthRefreshProvider
from .network import SafeOAuthHttpTransport, public_connection_pool
from .provider import DiscoveredPersonalOAuthProvider
from .refresh import StoredPersonalOAuthRefreshProvider


@asynccontextmanager
async def configured_personal_oauth_provider() -> AsyncIterator[PersonalOAuthProvider]:
    async with public_connection_pool() as pool:
        yield DiscoveredPersonalOAuthProvider(transport=SafeOAuthHttpTransport(pool=pool))


@asynccontextmanager
async def configured_personal_oauth_refresh_provider() -> AsyncIterator[PersonalOAuthRefreshProvider]:
    async with public_connection_pool() as pool:
        yield StoredPersonalOAuthRefreshProvider(transport=SafeOAuthHttpTransport(pool=pool))
