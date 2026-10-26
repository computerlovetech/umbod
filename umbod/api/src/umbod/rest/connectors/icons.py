from collections.abc import AsyncIterator

from umbod.core.icons import FaviconDiscovery, StrategyFaviconDiscovery
from umbod.core.icons.adapters.http import PublicFaviconHttpClient
from umbod.core.network import public_http_connection_pool
from umbod.core.icons.http_models import FaviconHttpPolicy
from umbod.core.icons.web_strategies import HtmlIconStrategy, OriginFaviconStrategy


async def get_favicon_discovery() -> AsyncIterator[FaviconDiscovery]:
    async with public_http_connection_pool(max_connections=4) as pool:
        client = PublicFaviconHttpClient(
            pool,
            FaviconHttpPolicy(max_body_bytes=262_144, max_redirects=3, timeout_seconds=1.0),
        )
        yield StrategyFaviconDiscovery(
            batches=((OriginFaviconStrategy(client), HtmlIconStrategy(client)),),
            strategy_timeout_seconds=1.0,
            overall_timeout_seconds=1.5,
        )
