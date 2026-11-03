from umbod.core.connectors.downstream_mcp.adapters.settings import (
    downstream_mcp_infrastructure_settings_from_app_config,
)
from umbod.rest.settings import APISettings


def test_downstream_mcp_settings_maps_only_resolved_downstream_concerns() -> None:
    app_settings = APISettings(
        connector_security={"configuration_secret": "credential-secret"},
        mcp={"downstream_discovery_timeout_seconds": 23.0},
    )

    settings = downstream_mcp_infrastructure_settings_from_app_config(app_settings)

    assert settings.credential_secret == "credential-secret"
    assert settings.tls_verification is True
    assert settings.connection_timeout_seconds == 10.0
    assert settings.discovery_timeout_seconds == 23.0
