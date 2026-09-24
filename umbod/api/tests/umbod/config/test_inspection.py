import json
from collections.abc import Sequence
from typing import Any

import pytest

from umbod.config import (
    AdminAuthConfig,
    AppConfig,
    AppConfigInspector,
    McpConfig,
    OidcConfig,
    OperatorSettings,
    RuntimeConfig,
    inspect_app_config,
    safe_app_config_dump,
)
from umbod.config.inspection import ConfigurationEntry

_SECRET_FIELDS = {
    "client_secret",
    "jwt_signing_key",
    "encryption_key",
    "configuration_secret",
    "approval_state_key",
    "test_bearer_token",
}
_NON_PRODUCTION_USER_VARIABLES = {
    "UMBOD_INTERNAL_API_ORIGIN",
    "UMBOD_REST_PORT",
    "UMBOD_REST_METRICS_PORT",
    "UMBOD_MCP_PORT",
    "UMBOD_MCP_METRICS_PORT",
    "UMBOD_MCP_TEST_USER_EMAIL",
    "UMBOD_MCP_TEST_USER_GROUP",
    "UMBOD_OAUTH_STORAGE_DIRECTORY",
    "UMBOD_CONNECTOR_STORE_SQLITE_PATH",
    "UMBOD_ADMIN_AUTHENTICATION_SIMULATED_ADMIN",
    "UMBOD_ADMIN_AUTHENTICATION_SIMULATED_USER_ID",
    "UMBOD_ADMIN_AUTHENTICATION_SIMULATED_USER_EMAIL",
    "UMBOD_ADMIN_AUTHENTICATION_SIMULATED_USER_NAME",
}
_SECRET_VARIABLES = {
    "UMBOD_ROOT_SECRET",
    "UMBOD_OIDC_CLIENT_SECRET",
    "UMBOD_MCP_TEST_BEARER_TOKEN",
}
_DERIVED_SECRET_VARIABLES = {
    "UMBOD_JWT_SIGNING_KEY",
    "UMBOD_TOKEN_ENCRYPTION_KEY",
    "UMBOD_CONNECTOR_CONFIGURATION_SECRET",
    "UMBOD_CONNECTOR_APPROVAL_STATE_KEY",
}


def _entries(config: AppConfig) -> list[ConfigurationEntry]:
    return [entry for group in AppConfigInspector(config).inspect() for entry in group.entries]


def _assert_value_matches_declared_type(entry: ConfigurationEntry) -> None:
    expected_types: dict[str, type[Any]] = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "string_list": list,
    }
    assert type(entry.value) is expected_types[entry.type]
    if entry.type == "string_list":
        assert all(isinstance(item, str) for item in entry.value)


def test_inspector_returns_effective_typed_values() -> None:
    config = AppConfig(
        runtime=RuntimeConfig(
            app_name="inspected-instance",
            profile="production",
            auth="auth0",
        ),
        mcp=McpConfig(
            connector_code_execution_timeout_seconds=12.5,
            downstream_discovery_concurrency=7,
            downstream_discovery_enabled=True,
        ),
        oidc=OidcConfig(provider="auth0", required_scopes=["openid", "profile"]),
        admin_authentication=AdminAuthConfig(mode="jwt", environment="production"),
    )

    entries = {entry.variable: entry for entry in _entries(config)}

    assert entries["UMBOD_APP_NAME"].value == "inspected-instance"
    assert entries["UMBOD_MCP_CODE_EXECUTION_TIMEOUT_SECONDS"].value == 12.5
    assert entries["UMBOD_MCP_DOWNSTREAM_DISCOVERY_CONCURRENCY"].value == 7
    assert entries["UMBOD_MCP_DOWNSTREAM_DISCOVERY_ENABLED"].value is True
    assert entries["UMBOD_FEATURE_MCP_ADMINISTRATOR_ENABLED"].value is True
    assert entries["UMBOD_OIDC_REQUIRED_SCOPES"].value == ["openid", "profile"]
    assert entries["UMBOD_AUTH"].value == "auth0"
    assert entries["UMBOD_PROFILE"].value == "production"
    for entry in entries.values():
        _assert_value_matches_declared_type(entry)


def test_catalog_order_is_deterministic_and_canonical_variables_are_unique() -> None:
    first = inspect_app_config(AppConfig()).model_dump()
    second = inspect_app_config(AppConfig()).model_dump()
    variables = [entry["variable"] for group in first["groups"] for entry in group["entries"]]

    assert first == second
    assert len(variables) == len(set(variables))
    assert [group["id"] for group in first["groups"]] == [
        "runtime",
        "endpoints",
        "features",
        "mcp",
        "identity",
        "storage",
        "openapi",
        "security",
    ]


def test_inspector_omits_development_and_deployment_plumbing() -> None:
    variables = {entry.variable for entry in _entries(AppConfig())}

    assert variables.isdisjoint(_NON_PRODUCTION_USER_VARIABLES)
    assert variables.isdisjoint(_DERIVED_SECRET_VARIABLES)


def test_catalog_variables_use_operator_canonical_names_or_documented_derived_sources() -> None:
    operator_names = {
        alias
        for field_name, field in OperatorSettings.model_fields.items()
        for alias in (
            f"UMBOD_{field_name.upper()}",
            field.validation_alias,
        )
        if isinstance(alias, str) and alias.startswith("UMBOD_")
    }
    variables = {entry.variable for entry in _entries(AppConfig())}

    assert variables <= operator_names


@pytest.mark.parametrize("secret_value", ["", "distinct-secret-value"])
def test_public_serializers_omit_every_known_secret_field_name_and_value(
    secret_value: str,
) -> None:
    config = AppConfig(
        oidc=OidcConfig(client_secret=secret_value, jwt_signing_key=secret_value),
        mcp=McpConfig(test_bearer_token=secret_value),
        oauth_storage={"encryption_key": secret_value},
        connector_security={"configuration_secret": secret_value},
    )

    public_documents: Sequence[dict[str, Any]] = [
        inspect_app_config(config).model_dump(),
        safe_app_config_dump(config),
    ]

    for document in public_documents:
        serialized = json.dumps(document)
        assert _SECRET_FIELDS.isdisjoint(serialized.split('"'))
        assert _SECRET_VARIABLES.isdisjoint(serialized.split('"'))
        assert "***" not in serialized
        if secret_value:
            assert secret_value not in serialized
    safe_dump = safe_app_config_dump(config)
    assert all(
        secret_field not in safe_dump.get(section, {})
        for section in safe_dump
        for secret_field in _SECRET_FIELDS
    )


def test_every_public_entry_has_operator_metadata() -> None:
    for entry in _entries(AppConfig()):
        assert entry.label.strip()
        assert entry.description.strip()
