from pydantic import Field
from pydantic_settings import BaseSettings

from umbod.config.operator import OperatorSettings


class ServerRootSettings(BaseSettings):
    model_config = OperatorSettings.model_config

    root_secret: str = Field(validation_alias="UMBOD_ROOT_SECRET", repr=False)
