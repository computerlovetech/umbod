from umbod.core.administrator.connector_configuration import (
    AdministratorConnectorConfiguration,
)
from umbod.mcp.administrator.authorization import administrator_authorization_check
from umbod.mcp.administrator.tools import AdministratorConnectorConfigurationTools
from umbod.mcp.tools import McpObservedToolRegistrar


def register_administrator_connector_configuration_tools(
    registrar: McpObservedToolRegistrar,
    configuration: AdministratorConnectorConfiguration,
    membership_claim: str,
    required_membership: str,
) -> None:
    authorization = administrator_authorization_check(
        membership_claim, required_membership
    )
    tools = AdministratorConnectorConfigurationTools(configuration, membership_claim)
    registrar.register(
        tools.read_connector_configuration,
        name="read_connector_configuration",
        description="Read the configurable state of an existing connector.",
        auth=authorization,
    )
    registrar.register(
        tools.upsert_connector_configuration,
        name="upsert_connector_configuration",
        description="Apply a partial desired configuration to an existing connector.",
        auth=authorization,
    )
