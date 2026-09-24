from umbod.config.app import ConnectorSecurityConfig


from umbod.config.defaults import LOCAL_DOWNSTREAM_MCP_CREDENTIAL_SECRET

DEFAULT_DOWNSTREAM_MCP_CREDENTIAL_SECRET = LOCAL_DOWNSTREAM_MCP_CREDENTIAL_SECRET


def resolve_downstream_mcp_credential_secret(settings: ConnectorSecurityConfig) -> str:
    return settings.configuration_secret or DEFAULT_DOWNSTREAM_MCP_CREDENTIAL_SECRET
