from typing import Literal

from fastmcp.exceptions import ToolError

from umbod.core.administrator.connector_configuration import (
    AdministratorConnectorConfiguration,
    ConfigurationRejected,
    ConnectorConfigurableState,
    ConnectorDesiredState,
    ConnectorReference,
    ReadConnectorConfiguration,
    UpsertConnectorConfiguration,
)
from umbod.mcp.administrator.principal import current_administrator_principal


class AdministratorConnectorConfigurationTools:
    def __init__(
        self,
        configuration: AdministratorConnectorConfiguration,
        membership_claim: str,
    ) -> None:
        self._configuration = configuration
        self._membership_claim = membership_claim

    async def read_connector_configuration(
        self, connector_kind: Literal["openapi"], connector_id: str
    ) -> ConnectorConfigurableState:
        result = await self._configuration.read(
            ReadConnectorConfiguration(
                principal=current_administrator_principal(self._membership_claim),
                connector=ConnectorReference(
                    connector_kind=connector_kind,
                    connector_id=connector_id,
                ),
            )
        )
        if isinstance(result, ConfigurationRejected):
            raise ToolError(result.error.message)
        return result.state

    async def upsert_connector_configuration(
        self,
        connector_kind: Literal["openapi"],
        connector_id: str,
        desired_state: ConnectorDesiredState,
    ) -> ConnectorConfigurableState:
        result = await self._configuration.upsert(
            UpsertConnectorConfiguration(
                principal=current_administrator_principal(self._membership_claim),
                connector=ConnectorReference(
                    connector_kind=connector_kind,
                    connector_id=connector_id,
                ),
                desired_state=desired_state,
            )
        )
        if isinstance(result, ConfigurationRejected):
            raise ToolError(result.error.message)
        return result.state
