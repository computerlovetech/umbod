from typing import Literal, Protocol

from pydantic import ConfigDict, SecretStr, field_validator

from umbod.proxies import Model
from umbod.core.configuration import (
    ConnectorConfigurationNotFoundError,
    ConnectorConfigurationService,
)


class OpenApiBearerConfiguration(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    bearer_token: SecretStr

    @field_validator("bearer_token")
    @classmethod
    def validate_bearer_token(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("Bearer token must not be blank")
        return SecretStr(value.get_secret_value().strip())


class OpenApiConfigurationStatus(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    configured: bool
    authentication_type: Literal["none", "bearer"]


class OpenApiConfigurationPort(Protocol):
    async def status(self, connector_id: str) -> OpenApiConfigurationStatus: ...

    async def configure(self, connector_id: str, bearer_token: SecretStr) -> OpenApiConfigurationStatus: ...

    async def clear(self, connector_id: str) -> OpenApiConfigurationStatus: ...

    async def resolve(self, connector_id: str) -> OpenApiBearerConfiguration | None: ...


class OpenApiConfigurationAdapter:
    def __init__(self, service: ConnectorConfigurationService) -> None:
        self._service = service

    async def status(self, connector_id: str) -> OpenApiConfigurationStatus:
        configured = await self.resolve(connector_id) is not None
        return OpenApiConfigurationStatus(
            configured=configured,
            authentication_type="bearer" if configured else "none",
        )

    async def configure(
        self, connector_id: str, bearer_token: SecretStr
    ) -> OpenApiConfigurationStatus:
        normalized = bearer_token.get_secret_value().strip()
        if not normalized:
            return await self.status(connector_id)
        await self._service.save_current_configuration(
            connector_id, OpenApiBearerConfiguration(bearer_token=SecretStr(normalized))
        )
        return OpenApiConfigurationStatus(configured=True, authentication_type="bearer")

    async def clear(self, connector_id: str) -> OpenApiConfigurationStatus:
        await self._service.delete_current_configuration(connector_id)
        return OpenApiConfigurationStatus(configured=False, authentication_type="none")

    async def resolve(self, connector_id: str) -> OpenApiBearerConfiguration | None:
        try:
            return await self._service.get_connector_configuration(
                connector_id, OpenApiBearerConfiguration
            )
        except ConnectorConfigurationNotFoundError:
            return None
