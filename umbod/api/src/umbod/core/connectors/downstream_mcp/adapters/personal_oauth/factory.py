from collections.abc import AsyncIterator
from ...management import utc_clock

from ...personal.oauth.applications import PersonalOAuthApplicationStore
from contextlib import asynccontextmanager

from ...personal.oauth.authorization import PersonalOAuthProvider
from ...personal.oauth.refresh import PersonalOAuthRefreshProvider
from .callback import CallbackURLPolicy
from .network import SafeOAuthHttpTransport
from umbod.core.network import public_http_connection_pool
from .provider import DiscoveredPersonalOAuthProvider
from .refresh import StoredPersonalOAuthRefreshProvider
from .setup import DiscoveredPersonalOAuthSetupProvider
from ...personal.oauth.setup import PersonalOAuthSetupProvider


@asynccontextmanager
async def configured_personal_oauth_provider(callback_policy: CallbackURLPolicy, applications: PersonalOAuthApplicationStore) -> AsyncIterator[PersonalOAuthProvider]:
    async with public_http_connection_pool(max_connections=10) as pool:
        yield DiscoveredPersonalOAuthProvider(callback_policy=callback_policy, transport=SafeOAuthHttpTransport(pool=pool), applications=applications, clock=utc_clock)


@asynccontextmanager
async def configured_personal_oauth_setup_provider(callback_policy: CallbackURLPolicy) -> AsyncIterator[PersonalOAuthSetupProvider]:
    async with public_http_connection_pool(max_connections=10) as pool:
        yield DiscoveredPersonalOAuthSetupProvider(callback_policy=callback_policy, transport=SafeOAuthHttpTransport(pool=pool))


@asynccontextmanager
async def configured_personal_oauth_refresh_provider(callback_policy: CallbackURLPolicy, applications: PersonalOAuthApplicationStore) -> AsyncIterator[PersonalOAuthRefreshProvider]:
    async with public_http_connection_pool(max_connections=10) as pool:
        yield StoredPersonalOAuthRefreshProvider(callback_policy=callback_policy, transport=SafeOAuthHttpTransport(pool=pool), applications=applications, clock=utc_clock)
