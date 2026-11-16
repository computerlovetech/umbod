from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from ...personal_connections.oauth_ports import PersonalOAuthProvider
from ...personal_connections.refresh_provider_ports import PersonalOAuthRefreshProvider
from .callback import CallbackURLPolicy
from .network import SafeOAuthHttpTransport
from umbod.core.network import public_http_connection_pool
from .provider import DiscoveredPersonalOAuthProvider
from .refresh import StoredPersonalOAuthRefreshProvider
from .setup import DiscoveredPersonalOAuthSetupProvider
from ...personal_oauth_setup.ports import PersonalOAuthSetupProvider


@asynccontextmanager
async def configured_personal_oauth_provider(callback_policy: CallbackURLPolicy) -> AsyncIterator[PersonalOAuthProvider]:
    async with public_http_connection_pool(max_connections=10) as pool:
        yield DiscoveredPersonalOAuthProvider(callback_policy=callback_policy, transport=SafeOAuthHttpTransport(pool=pool))


@asynccontextmanager
async def configured_personal_oauth_setup_provider(callback_policy: CallbackURLPolicy) -> AsyncIterator[PersonalOAuthSetupProvider]:
    async with public_http_connection_pool(max_connections=10) as pool:
        yield DiscoveredPersonalOAuthSetupProvider(callback_policy=callback_policy, transport=SafeOAuthHttpTransport(pool=pool))


@asynccontextmanager
async def configured_personal_oauth_refresh_provider(callback_policy: CallbackURLPolicy) -> AsyncIterator[PersonalOAuthRefreshProvider]:
    async with public_http_connection_pool(max_connections=10) as pool:
        yield StoredPersonalOAuthRefreshProvider(callback_policy=callback_policy, transport=SafeOAuthHttpTransport(pool=pool))
