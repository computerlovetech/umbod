from typing import Annotated, Literal

from pydantic import ConfigDict, Field, WithJsonSchema

from umbod.proxies import Model
from umbod.core.connectors.portable.managed.catalog_models import (
    ManagedConfigurationField,
    ManagedConnectorConfiguration,
    ManagedConnectorSummary,
    SavedConfiguration,
)
from umbod.core.connectors.portable.managed.configuration_schema import (
    MAX_CONFIGURATION_FIELDS,
)


class ConnectorList(Model):
    connectors: tuple[ManagedConnectorSummary, ...]


class _ConnectorWithFields(Model):
    connector: ManagedConnectorSummary
    fields: tuple[ManagedConfigurationField, ...]


class SavedConnectorConfigurationResponse(_ConnectorWithFields):
    configuration: dict[str, str] = Field(repr=False)


class UnconfiguredConnectorResponse(_ConnectorWithFields):
    configuration: Literal[None]


type ConnectorConfigurationResponse = (
    SavedConnectorConfigurationResponse | UnconfiguredConnectorResponse
)


def configuration_response(
    managed: ManagedConnectorConfiguration,
) -> ConnectorConfigurationResponse:
    saved = managed.configuration
    if isinstance(saved, SavedConfiguration):
        return SavedConnectorConfigurationResponse(
            connector=managed.connector,
            fields=managed.fields,
            configuration=saved.values,
        )
    return UnconfiguredConnectorResponse(
        connector=managed.connector, fields=managed.fields, configuration=None
    )


class ConfigurationInput(Model):
    model_config = ConfigDict(extra="forbid", strict=True)

    configuration: Annotated[
        dict[str, Annotated[object, WithJsonSchema({"type": "string"})]],
        Field(max_length=MAX_CONFIGURATION_FIELDS, repr=False),
    ]
