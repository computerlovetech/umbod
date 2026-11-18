from umbod.core.administrator.connector_configuration import (
    AdministratorConnectorConfiguration,
)
from umbod.mcp.administrator.authorization import administrator_authorization_check
from umbod.mcp.administrator.connector_configuration.tools import AdministratorConnectorConfigurationTools
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
        builtin_response=True,
    )
    registrar.register(
        tools.upsert_connector_configuration,
        name="upsert_connector_configuration",
        description=(
            "Apply a partial desired state to an existing connector. Omitted or empty "
            "operations read the current configuration without changes. Invocation policy "
            "operations support only tool capabilities. Do not repeat an activation target "
            "or an invocation policy target within its own operation type; activation and "
            "policy for the same tool may be combined. Use at most one description "
            "operation across override (set_capability_description) and restore "
            "(use_system_capability_description). Use at most one permission operation "
            "per group, with unique capability targets within that group."
        ),
        auth=authorization,
        builtin_response=True,
    )
