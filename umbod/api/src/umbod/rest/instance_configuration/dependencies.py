from typing import Annotated

from fastapi import Depends

from umbod.config import AppConfig
from umbod.config.inspection import AppConfigInspector, InstanceConfigurationInspector


def get_app_config() -> AppConfig:
    raise RuntimeError("Application configuration dependency is not wired")


def get_instance_configuration_inspector(
    config: Annotated[AppConfig, Depends(get_app_config)],
) -> InstanceConfigurationInspector:
    return AppConfigInspector(config)
