from dataclasses import dataclass

from umbod.config import AppConfig
from umbod.core.connectors.downstream_mcp.security import resolve_downstream_mcp_credential_secret


@dataclass(frozen=True)
class DownstreamMcpInfrastructureSettings:
    credential_secret: str
    tls_verification: bool
    connection_timeout_seconds: float
    discovery_timeout_seconds: float
    oauth_enabled: bool = False


def downstream_mcp_infrastructure_settings_from_app_config(
    settings: AppConfig,
) -> DownstreamMcpInfrastructureSettings:
    return DownstreamMcpInfrastructureSettings(
        credential_secret=resolve_downstream_mcp_credential_secret(settings.connector_security),
        tls_verification=True,
        connection_timeout_seconds=10.0,
        discovery_timeout_seconds=settings.mcp.downstream_discovery_timeout_seconds,
        oauth_enabled=settings.mcp.downstream_oauth_enabled,
    )
