import asyncio

from umbod.config import load_app_config
from umbod.logging import configure_logging
from umbod.mcp.public_app import create_configured_production_app

settings = load_app_config(".env")
configure_logging(settings.runtime.app_name, settings.runtime.log_level)
app = asyncio.run(create_configured_production_app(settings))
