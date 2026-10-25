from dataclasses import dataclass

from umbod.config import AppConfig
from ..personal_connections.identity_models import PersonalIdentityPolicy
from umbod.core.connectors.downstream_mcp.security import resolve_downstream_mcp_credential_secret


def personal_identity_policy_from_app_config(settings: AppConfig) -> PersonalIdentityPolicy:
    return PersonalIdentityPolicy(
        enabled=settings.personal_connections.enabled,
        identity_namespace=settings.personal_connections.identity_namespace,
        authentication_mode=settings.admin_authentication.mode,
        authentication_environment=settings.admin_authentication.environment,
        runtime_profile=settings.runtime.profile,
        runtime_auth=settings.runtime.auth,
        provider=settings.oidc.provider,
        expected_issuer=settings.oidc.issuer_url,
        expected_tenant=settings.oidc.tenant_id,
        simulated_subject=settings.admin_authentication.simulated_user_id,
    )


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
