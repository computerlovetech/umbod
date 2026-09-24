from collections.abc import Sequence

from umbod.proxies import Model

from umbod.core.connectors.native.models import ConnectorConfigurationCheckResult
from umbod.core.connectors.native.registry.domain import (
    ConnectorDefinition,
    ConnectorDefinitionFilter,
    ConnectorRegistration,
    ConnectorRegistry,
)
from umbod.core.connectors.native.registry.builder import default_configuration_check
from umbod.core.connectors.native.registry.registration import (
    connector_definitions_from_registrations,
)


class _InMemoryConnectorRegistry:
    def __init__(self, connector_definitions: Sequence[ConnectorDefinition]) -> None:
        self._connector_definitions = list(connector_definitions)

    def list_connector_definitions(
        self,
        filters: ConnectorDefinitionFilter,
    ) -> list[ConnectorDefinition]:
        return [
            connector_definition
            for connector_definition in self._connector_definitions
            if filters.availability == "registered" or connector_definition.available
        ]

    def get_connector_definition(
        self,
        connector_id: str,
        filters: ConnectorDefinitionFilter,
    ) -> ConnectorDefinition | None:
        return next(
            (
                connector_definition
                for connector_definition in self.list_connector_definitions(filters)
                if connector_definition.metadata.id == connector_id
            ),
            None,
        )

    def check_configuration(
        self,
        connector_id: str,
        configuration: Model,
    ) -> ConnectorConfigurationCheckResult:
        connector_definition = self.get_connector_definition(
            connector_id,
            ConnectorDefinitionFilter(availability="registered"),
        )
        if connector_definition is None:
            return _configuration_check_result(default_configuration_check(configuration))
        return _configuration_check_result(connector_definition.configuration_check(configuration))


def InMemoryConnectorRegistry(
    registrations: Sequence[ConnectorRegistration],
    available_connector_ids: Sequence[str],
) -> ConnectorRegistry:
    return _InMemoryConnectorRegistry(
        connector_definitions_from_registrations(registrations, available_connector_ids)
    )


def _configuration_check_result(
    result: bool | ConnectorConfigurationCheckResult,
) -> ConnectorConfigurationCheckResult:
    if isinstance(result, ConnectorConfigurationCheckResult):
        return result
    if hasattr(result, "valid"):
        return ConnectorConfigurationCheckResult.model_validate(result.model_dump())
    if result:
        return ConnectorConfigurationCheckResult(valid=True)
    return ConnectorConfigurationCheckResult(
        valid=False,
        message="Connector configuration must be valid before publishing",
    )
