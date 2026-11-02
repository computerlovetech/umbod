from typing import Literal

from umbod.core.administrator.connector_configuration import (
    AdministratorConnectorConfiguration,
    ConfigurationRejected,
    ConnectorConfigurableState,
    ConnectorDesiredState,
    ConnectorReference,
    ReadConnectorConfiguration,
    UpsertConnectorConfiguration,
)
from umbod.mcp.administrator.errors import configuration_rejection_error
from umbod.mcp.administrator.principal import current_administrator_principal
from umbod.mcp.responses.progress import operation_completed, operation_started


class AdministratorConnectorConfigurationTools:
    def __init__(
        self,
        configuration: AdministratorConnectorConfiguration,
        membership_claim: str,
    ) -> None:
        self._configuration = configuration
        self._membership_claim = membership_claim

    async def read_connector_configuration(
        self, connector_kind: Literal["native", "openapi", "downstream_mcp"], connector_id: str
    ) -> ConnectorConfigurableState:
        request = ReadConnectorConfiguration(
            principal=current_administrator_principal(self._membership_claim),
            connector=ConnectorReference(
                connector_kind=connector_kind,
                connector_id=connector_id,
            ),
        )
        operation_started()
        result = await self._configuration.read(request)
        if isinstance(result, ConfigurationRejected):
            raise configuration_rejection_error(result)
        operation_completed()
        return result.state

    async def upsert_connector_configuration(
        self,
        connector_kind: Literal["native", "openapi", "downstream_mcp"],
        connector_id: str,
        desired_state: ConnectorDesiredState,
    ) -> ConnectorConfigurableState:
        request = UpsertConnectorConfiguration(
            principal=current_administrator_principal(self._membership_claim),
            connector=ConnectorReference(
                connector_kind=connector_kind,
                connector_id=connector_id,
            ),
            desired_state=desired_state,
        )
        operation_started()
        result = await self._configuration.upsert(request)
        if isinstance(result, ConfigurationRejected):
            raise configuration_rejection_error(result)
        operation_completed()
        return result.state
