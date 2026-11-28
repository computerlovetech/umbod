from collections.abc import Mapping
from dataclasses import replace
from uuid import UUID

from .catalog_models import (
    ManagedConfigurationField,
    ManagedConfigurationFieldRejected,
    ManagedConfigurationRejected,
    ManagedConnectorConfiguration,
    ManagedConnectorSummary,
    SavedConfiguration,
)
from .ports import ManagedConnectorCatalogStore


class PortableConnectorCatalog:
    def __init__(self, store: ManagedConnectorCatalogStore) -> None:
        self._store = store

    async def list_connectors(self) -> tuple[ManagedConnectorSummary, ...]:
        return await self._store.list_connectors()

    async def read_configuration(
        self, connector_id: UUID
    ) -> ManagedConnectorConfiguration:
        return await self._store.read_configuration(connector_id)

    async def replace_configuration(
        self,
        connector: ManagedConnectorConfiguration,
        values: Mapping[str, object],
    ) -> ManagedConnectorConfiguration:
        configuration = validate_configuration(connector.fields, values)
        await self._store.replace_configuration(
            connector.connector.connector_id, configuration
        )
        return replace(
            connector,
            connector=replace(connector.connector, configured=True),
            configuration=configuration,
        )


def validate_configuration(
    fields: tuple[ManagedConfigurationField, ...],
    values: Mapping[str, object],
) -> SavedConfiguration:
    if values.keys() - {field.name for field in fields}:
        raise ManagedConfigurationRejected("unknown_field")
    validated: dict[str, str] = {}
    for field in fields:
        if field.name in values:
            validated[field.name] = _validate_value(field, values[field.name])
        elif field.required:
            raise ManagedConfigurationFieldRejected("required_field", field.name)
    return SavedConfiguration(validated)


def _validate_value(field: ManagedConfigurationField, value: object) -> str:
    if not isinstance(value, str):
        raise ManagedConfigurationFieldRejected("invalid_type", field.name)
    if not field.min_length <= len(value) <= field.max_length:
        raise ManagedConfigurationFieldRejected("invalid_length", field.name)
    if field.choices and value not in field.choices:
        raise ManagedConfigurationFieldRejected("invalid_choice", field.name)
    if "\r" in value or "\n" in value:
        raise ManagedConfigurationFieldRejected("invalid_value", field.name)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ManagedConfigurationFieldRejected("invalid_value", field.name) from None
    return value
