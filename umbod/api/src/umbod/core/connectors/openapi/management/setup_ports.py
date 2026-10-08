from typing import Literal, Protocol

from pydantic import ConfigDict, SecretStr

from umbod.core.capabilities.descriptions import CapabilityDescription
from umbod.core.connectors.openapi.management.models import (
    CreateOpenApiConnector,
    ImportOpenApiCatalog,
    OpenApiConnector,
    OpenApiConnectorCatalog,
)
from umbod.proxies import Model


class SetupOpenApiConnector(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: str
    tool_name_prefix: str
    capability_description: CapabilityDescription
    document: dict[str, object]
    approved_hosts: tuple[str, ...]
    authentication_type: Literal["none", "bearer"]
    bearer_token: SecretStr


class OpenApiSetupManagementPort(Protocol):
    async def create_connector(self, request: CreateOpenApiConnector) -> OpenApiConnector: ...

    async def import_catalog(self, request: ImportOpenApiCatalog) -> OpenApiConnectorCatalog: ...

    async def delete_connector(self, connector_id: str) -> None: ...

    async def get_connector(self, connector_id: str) -> OpenApiConnector: ...


class OpenApiConnectorSetupPort(Protocol):
    async def setup(self, request: SetupOpenApiConnector) -> OpenApiConnector: ...


class OpenApiSetupInvalidRequest(ValueError):
    pass


class OpenApiSetupFailed(Exception):
    pass


class OpenApiSetupCleanupFailed(Exception):
    def __init__(self, connector_id: str) -> None:
        super().__init__("OpenAPI setup cleanup failed")
        self.connector_id = connector_id
