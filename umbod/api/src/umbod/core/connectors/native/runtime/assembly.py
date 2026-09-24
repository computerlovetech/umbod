from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from umbod.core.configuration import ConnectorCurrentConfigurationStore
from umbod.core.connectors.native.deployment import DeploymentConnectorAvailability
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.connectors.native.registry import ConnectorRegistration
from umbod.core.connectors.native.runtime.mappings import (
    ConnectorPromptMapping,
    ConnectorResourceMapping,
    connector_prompt_mappings,
    connector_resource_mappings,
    connector_tool_mappings,
)
from umbod.core.connectors.native.runtime.tools import ConnectorToolMapping

from umbod.core.connectors.native.plugin import ConnectorPlugin


@dataclass(frozen=True)
class ConnectorRuntime:
    connector_registrations: Sequence[Mapping[str, object]]
    connector_configuration_store: ConnectorCurrentConfigurationStore | None
    connector_publishing_store: ConnectorPublishingStore | None
    connector_tool_mappings: Sequence[ConnectorToolMapping]
    connector_prompt_mappings: Sequence[ConnectorPromptMapping] = ()
    connector_resource_mappings: Sequence[ConnectorResourceMapping] = ()


class _ConnectorRuntimeParts:
    def __init__(self) -> None:
        self.connector_registrations: list[ConnectorRegistration] = []
        self.connector_tool_mappings: list[ConnectorToolMapping] = []
        self.connector_prompt_mappings: list[ConnectorPromptMapping] = []
        self.connector_resource_mappings: list[ConnectorResourceMapping] = []

    def append_plugin_runtime(
        self,
        *,
        plugin: ConnectorPlugin,
        configuration_store: ConnectorCurrentConfigurationStore,
    ) -> None:
        definition = plugin.definition()
        registration = plugin.registration()
        self.connector_registrations.append(registration)
        self.connector_tool_mappings.extend(
            connector_tool_mappings(
                definition,
                tool_name_prefix=str(registration["tool_name_prefix"]),
                configuration_store=configuration_store,
            )
        )
        self.connector_prompt_mappings.extend(
            connector_prompt_mappings(
                definition,
                configuration_store=configuration_store,
            )
        )
        self.connector_resource_mappings.extend(
            connector_resource_mappings(
                definition,
                configuration_store=configuration_store,
            )
        )

    def to_runtime(
        self,
        *,
        configuration_store: ConnectorCurrentConfigurationStore,
        publishing_store: ConnectorPublishingStore,
    ) -> ConnectorRuntime:
        return ConnectorRuntime(
            connector_registrations=self.connector_registrations,
            connector_configuration_store=configuration_store,
            connector_publishing_store=publishing_store,
            connector_tool_mappings=self.connector_tool_mappings,
            connector_prompt_mappings=self.connector_prompt_mappings,
            connector_resource_mappings=self.connector_resource_mappings,
        )


def empty_connector_runtime() -> ConnectorRuntime:
    return ConnectorRuntime(
        connector_registrations=[],
        connector_configuration_store=None,
        connector_publishing_store=None,
        connector_tool_mappings=[],
    )


def assemble_connector_runtime(
    *,
    plugins: Sequence[ConnectorPlugin],
    availability: DeploymentConnectorAvailability,
    configuration_store: ConnectorCurrentConfigurationStore,
    publishing_store: ConnectorPublishingStore,
) -> ConnectorRuntime:
    plugins_by_id = index_connector_plugins(plugins)
    runtime_parts = _ConnectorRuntimeParts()
    for connector_id in availability.connector_ids:
        plugin = plugins_by_id.get(connector_id)
        if plugin is not None:
            runtime_parts.append_plugin_runtime(
                plugin=plugin,
                configuration_store=configuration_store,
            )
    return runtime_parts.to_runtime(
        configuration_store=configuration_store,
        publishing_store=publishing_store,
    )


def connector_registrations_from_plugins(
    plugins: Sequence[ConnectorPlugin],
) -> list[ConnectorRegistration]:
    return [plugin.registration() for plugin in plugins]


def index_connector_plugins(plugins: Sequence[ConnectorPlugin]) -> dict[str, ConnectorPlugin]:
    plugins_by_id: dict[str, ConnectorPlugin] = {}
    for plugin in plugins:
        connector_id = str(plugin.registration()["id"])
        if connector_id in plugins_by_id:
            raise ValueError(f"duplicate connector id: {connector_id}")
        plugins_by_id[connector_id] = plugin
    return plugins_by_id


__all__ = [
    "ConnectorRuntime",
    "assemble_connector_runtime",
    "connector_registrations_from_plugins",
    "empty_connector_runtime",
    "index_connector_plugins",
]
