from umbod.config.app import ConnectorSecurityConfig, ConnectorStoreConfig
from umbod.config.operator import OperatorSettings


def resolve_personal_connections_enabled(operator: OperatorSettings) -> bool:
    if operator.personal_connections_enabled == "auto":
        return bool(operator.personal_connections_identity_namespace)
    return operator.personal_connections_enabled


def resolve_personal_connections_oauth_enabled(
    operator: OperatorSettings,
    selection_enabled: bool,
    connector_store: ConnectorStoreConfig,
    connector_security: ConnectorSecurityConfig,
) -> bool:
    if operator.personal_connections_oauth_enabled == "auto":
        return (
            selection_enabled
            and connector_store.is_durable_sqlite
            and bool(connector_security.configuration_secret.strip())
        )
    return operator.personal_connections_oauth_enabled
