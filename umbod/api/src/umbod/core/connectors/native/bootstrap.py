from collections.abc import Sequence
from pydantic import BaseModel
from typing import Literal, Protocol

from umbod.config.defaults import LOCAL_CONNECTOR_CONFIGURATION_SECRET
from umbod.core.configuration import (
    ConnectorConfigurationRegistry,
    ConnectorConfigurationService,
    EncryptedConnectorConfigurationStoreProtocol,
    EnvironmentConnectorConfigurationSecret,
)
from umbod.core.connectors.native.deployment import (
    CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH_VARIABLE,
    deployment_connector_availability_source_from_environment,
)
from umbod.core.connectors.native.plugin import ConnectorPlugin
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.connectors.native.runtime import ConnectorRuntime, assemble_connector_runtime
from umbod.proxies import Model


class ConnectorSecuritySettingsPort(Protocol):
    configuration_secret: str


class ConnectorRuntimeSettingsPort(Protocol):
    connector_security: ConnectorSecuritySettingsPort


class ConnectorPluginLoader(Protocol):
    def __call__(self, include_diagnostics: Literal[False]) -> list[ConnectorPlugin]: ...


class EncryptedConnectorConfigurationStoreFactory(Protocol):
    async def __call__(self) -> EncryptedConnectorConfigurationStoreProtocol: ...


class ConnectorPublishingStoreFactory(Protocol):
    async def __call__(self) -> ConnectorPublishingStore: ...


class DefaultConnectorRuntimeFactory:
    def __init__(
        self,
        plugin_loader: ConnectorPluginLoader,
        configuration_store_factory: EncryptedConnectorConfigurationStoreFactory,
        publishing_store_factory: ConnectorPublishingStoreFactory,
    ) -> None:
        self._plugin_loader = plugin_loader
        self._configuration_store_factory = configuration_store_factory
        self._publishing_store_factory = publishing_store_factory

    async def create(self, settings: ConnectorRuntimeSettingsPort) -> ConnectorRuntime:
        plugins = self._plugin_loader(False)
        availability = deployment_connector_availability_source_from_environment(
            CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH_VARIABLE
        ).load()
        publishing_store = await self._publishing_store_factory()
        configuration_store = ConnectorConfigurationService(
            registry=_configuration_registry_from_plugins(plugins),
            store=await self._configuration_store_factory(),
            secret=EnvironmentConnectorConfigurationSecret.from_value(
                settings.connector_security.configuration_secret
                or LOCAL_CONNECTOR_CONFIGURATION_SECRET
            ),
        )
        return assemble_connector_runtime(
            plugins=plugins,
            availability=availability,
            configuration_store=configuration_store,
            publishing_store=publishing_store,
        )


async def create_default_connector_runtime(
    settings: ConnectorRuntimeSettingsPort,
    plugin_loader: ConnectorPluginLoader,
    configuration_store_factory: EncryptedConnectorConfigurationStoreFactory,
    publishing_store_factory: ConnectorPublishingStoreFactory,
) -> ConnectorRuntime:
    return await DefaultConnectorRuntimeFactory(
        plugin_loader, configuration_store_factory, publishing_store_factory
    ).create(settings)


def _configuration_registry_from_plugins(
    plugins: Sequence[ConnectorPlugin],
) -> ConnectorConfigurationRegistry:
    return ConnectorConfigurationRegistry(schemas=_configuration_schemas_from_plugins(plugins))


def _configuration_schemas_from_plugins(
    plugins: Sequence[ConnectorPlugin],
) -> dict[str, type[Model]]:
    schemas: dict[str, type[Model]] = {}
    for plugin in plugins:
        registration = plugin.registration()
        connector_id = registration.get("id")
        configuration_schema = registration.get("configuration_schema")
        if isinstance(connector_id, str) and _is_configuration_schema(configuration_schema):
            schemas[connector_id] = configuration_schema
    return schemas


def _is_configuration_schema(value: object) -> bool:
    return isinstance(value, type) and issubclass(value, BaseModel)


__all__ = [
    "ConnectorPluginLoader",
    "EncryptedConnectorConfigurationStoreFactory",
    "DefaultConnectorRuntimeFactory",
    "create_default_connector_runtime",
]
