from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.routing import Mount

from umbod.config import load_server_app_config
from umbod.hosting import create_mcp_app
from umbod.logging import configure_logging


@asynccontextmanager
async def lifespan(service: Starlette) -> AsyncIterator[None]:
    settings = load_server_app_config(".env")
    configure_logging(settings.runtime.app_name, settings.runtime.log_level)
    application = await create_mcp_app(settings, auth_provider=None, group_permission_runtime_state=None, invocation_log_sink=None)
    async with application.router.lifespan_context(application):
        mount = Mount("/", app=application)
        service.router.routes.append(mount)
        try:
            yield
        finally:
            service.router.routes.remove(mount)


app = Starlette(lifespan=lifespan)
