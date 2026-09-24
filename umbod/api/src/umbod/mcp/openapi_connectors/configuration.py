from fastmcp import FastMCP

from umbod.core.configuration import (
    ConnectorConfigurationRegistry,
    ConnectorConfigurationService,
    EnvironmentConnectorConfigurationSecret,
)
from umbod.core.connectors.openapi.management import (
    OpenApiBearerConfiguration,
    OpenApiConfigurationAdapter,
)


async def openapi_configuration_adapter(server: FastMCP) -> OpenApiConfigurationAdapter:
    service = ConnectorConfigurationService(
        registry=ConnectorConfigurationRegistry({'openapi': OpenApiBearerConfiguration}),
        store=server.openapi_configuration_store,
        secret=EnvironmentConnectorConfigurationSecret.from_value(server.openapi_configuration_secret),
    )
    return OpenApiConfigurationAdapter(service)
