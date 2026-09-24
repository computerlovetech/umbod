from collections.abc import Mapping, Sequence
from typing import cast

from fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, SkipValidation

from umbod.mcp.proxies import Model
from umbod.core.activation import ActivationStore
from umbod.core.configuration import ConnectorCurrentConfigurationStore
from umbod.core.publishing import (
    ConnectorPublishStateChangeSource,
    ConnectorPublishingStore,
)
from umbod.core.connectors.native.runtime import ConnectorResourceMapping
from umbod.proxies import Model as ConnectorConfigurationModel

from umbod.mcp.connectors.resources.registry import RuntimeConnectorResourceRegistry


class ConnectorResourceRegistrationOptions(Model):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
    )

    connector_registrations: Sequence[Mapping[str, object]] | None
    connector_configuration_store: SkipValidation[ConnectorCurrentConfigurationStore | None]
    connector_publishing_store: SkipValidation[ConnectorPublishingStore | None]
    activation_store: SkipValidation[ActivationStore | None]
    connector_resource_mappings: SkipValidation[Sequence[ConnectorResourceMapping] | None]


async def register_connector_resources(
    mcp: FastMCP,
    options: ConnectorResourceRegistrationOptions,
) -> None:
    if not _has_required_registration_options(options):
        return
    registry = RuntimeConnectorResourceRegistry(
        mcp,
        schemas=_valid_configuration_schemas(
            cast(Sequence[Mapping[str, object]], options.connector_registrations)
        ),
        connector_configuration_store=cast(
            ConnectorCurrentConfigurationStore, options.connector_configuration_store
        ),
        connector_publishing_store=cast(
            ConnectorPublishingStore, options.connector_publishing_store
        ),
        activation_store=cast(ActivationStore, options.activation_store),
        connector_resource_mappings=cast(
            Sequence[ConnectorResourceMapping], options.connector_resource_mappings
        ),
    )
    setattr(mcp, "connector_resource_registry", registry)
    await registry.reconcile_all()
    connector_publishing_store = options.connector_publishing_store
    if isinstance(connector_publishing_store, ConnectorPublishStateChangeSource):
        connector_publishing_store.subscribe_publish_state_changes(
            registry.handle_publish_state_changed
        )


def _has_required_registration_options(options: ConnectorResourceRegistrationOptions) -> bool:
    return bool(
        options.connector_registrations
        and options.connector_configuration_store is not None
        and options.connector_publishing_store is not None
        and options.activation_store is not None
        and options.connector_resource_mappings
    )


def _valid_configuration_schemas(
    registrations: Sequence[Mapping[str, object]],
) -> dict[str, type[ConnectorConfigurationModel]]:
    schemas: dict[str, type[ConnectorConfigurationModel]] = {}
    for registration in registrations:
        connector_id = registration.get("id")
        configuration_schema = registration.get("configuration_schema")
        if (
            isinstance(connector_id, str)
            and isinstance(configuration_schema, type)
            and issubclass(configuration_schema, BaseModel)
        ):
            schemas[connector_id] = configuration_schema
    return schemas
