from fastapi import FastAPI

from umbod.config.telemetry import load_telemetry_app_config
from umbod.logging import configure_logging
from umbod.rest.telemetry.application import create_telemetry_app


def create_app() -> FastAPI:
    settings = load_telemetry_app_config(".env")
    configure_logging(settings.runtime.app_name, settings.runtime.log_level)
    return create_telemetry_app(settings)
