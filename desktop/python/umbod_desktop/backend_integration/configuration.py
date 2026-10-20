from pathlib import Path

from umbod.config.secret_derivation import derive_secret
from umbod.hosting import AppConfig

from ..contracts import DESKTOP_GROUP
from ..settings import DesktopSettings


def desktop_settings(
    directory: Path, origin: str, root_secret: str, advanced: DesktopSettings
) -> AppConfig:
    return AppConfig.model_validate(
        {
            "runtime": {
                "app_name": "umbod-desktop",
                "profile": "desktop",
                "auth": "desktop",
            },
            "endpoints": {
                "site_base_url": origin,
                "api_base_url": origin,
                "private_api_base_url": origin,
                "mcp_base_url": origin,
            },
            "rest": {"metrics_enabled": False},
            "mcp": {
                "metrics_enabled": False,
                "auth_mode": "none",
                "messaging_transport": "sql",
                "permission_group_claim": "groups",
                "connector_tool_exposure_mode": advanced.connector_tool_exposure_mode,
                "downstream_oauth_enabled": True,
            },
            "admin_authentication": {
                "mode": "jwt",
                "environment": "production",
                "jwt_header_name": "Authorization",
                "membership_claim": "groups",
                "required_membership": DESKTOP_GROUP,
            },
            "connector_store": {
                "type": "sqlite",
                "sqlite_path": str(directory / "backend.sqlite3"),
            },
            "connector_security": {
                "configuration_secret": derive_secret(
                    root_secret, "connector-configuration"
                ),
                "approval_state_key": derive_secret(
                    root_secret, "connector-approval-state"
                ),
            },
            "oauth_storage": {
                "directory": str(directory / "oauth"),
                "encryption_key": derive_secret(root_secret, "oauth-token-storage"),
            },
            "feature_toggles": {
                "mcp_administrator_enabled": advanced.mcp_administrator_enabled
            },
            "cors": {"origins": []},
        }
    )
