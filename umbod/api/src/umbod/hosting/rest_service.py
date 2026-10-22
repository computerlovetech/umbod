from fastapi import FastAPI

from umbod.config import load_server_app_config
from umbod.hosting import create_rest_app
from umbod.logging import configure_logging


def create_app() -> FastAPI:
    settings = load_server_app_config(".env")
    configure_logging(settings.runtime.app_name, settings.runtime.log_level)
    return create_rest_app(settings, connector_registrations=None, admin_verifier=None, oauth_service=None)
