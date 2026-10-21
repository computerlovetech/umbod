import pytest
from pydantic import ValidationError

from umbod.config import OperatorSettings, build_app_config, inspect_app_config
from umbod.config.operator import PersonalConnectionsMode


@pytest.mark.parametrize("mode", ["auto", "true", "false"])
def test_personal_modes_parse_from_environment(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setenv("UMBOD_PERSONAL_CONNECTIONS_ENABLED", mode)
    monkeypatch.setenv("UMBOD_PERSONAL_CONNECTIONS_OAUTH_ENABLED", mode)
    monkeypatch.setenv("UMBOD_PERSONAL_CONNECTIONS_IDENTITY_NAMESPACE", "test:local")
    monkeypatch.setenv("UMBOD_CONNECTOR_STORE", "sqlite")
    monkeypatch.setenv("UMBOD_ROOT_SECRET", "policy-secret")
    operator = OperatorSettings(_env_file=None)
    expected_mode = "auto" if mode == "auto" else mode == "true"
    assert operator.personal_connections_enabled == expected_mode
    assert operator.personal_connections_oauth_enabled == expected_mode
    config = build_app_config(operator)
    assert config.personal_connections.enabled is (mode != "false")
    assert config.personal_connections.oauth_enabled is (mode != "false")


def test_operator_personal_modes_default_to_automatic() -> None:
    operator = OperatorSettings(_env_file=None)
    assert operator.personal_connections_enabled == "auto"
    assert operator.personal_connections_oauth_enabled == "auto"
    config = build_app_config(operator)
    assert config.personal_connections.enabled is False
    assert config.personal_connections.oauth_enabled is False


@pytest.mark.parametrize(
    "namespace,store,path,secret,selection,oauth",
    [
        ("", "sqlite", "durable.sqlite", "secret", False, False),
        ("test:local", "inmemory", "durable.sqlite", "secret", True, False),
        ("test:local", "sqlite", "", "secret", True, False),
        ("test:local", "sqlite", " ", "secret", True, False),
        ("test:local", "sqlite", ":memory:", "secret", True, False),
        ("test:local", "sqlite", "file::memory:", "secret", True, False),
        ("test:local", "sqlite", "file:db?mode=memory", "secret", True, False),
        ("test:local", "sqlite", "durable.sqlite", "", True, False),
        ("test:local", "sqlite", "durable.sqlite", " \t", True, False),
        ("test:local", "sqlite", "durable.sqlite", "secret", True, True),
        ("test:local", "sqlite", "file:db?mode=rwc", "secret", True, True),
    ],
)
def test_automatic_personal_policy_resolves_prerequisites_and_inspects_booleans(
    namespace: str,
    store: str,
    path: str,
    secret: str,
    selection: bool,
    oauth: bool,
) -> None:
    config = build_app_config(
        OperatorSettings(
            _env_file=None,
            personal_connections_identity_namespace=namespace,
            connector_store=store,
            connector_store_sqlite_path=path,
            root_secret=secret,
        )
    )
    assert config.personal_connections.enabled is selection
    assert config.personal_connections.oauth_enabled is oauth
    entries = {
        entry.variable: entry
        for group in inspect_app_config(config).groups
        for entry in group.entries
    }
    for variable, expected in (
        ("UMBOD_PERSONAL_CONNECTIONS_ENABLED", selection),
        ("UMBOD_PERSONAL_CONNECTIONS_OAUTH_ENABLED", oauth),
    ):
        assert entries[variable].type == "boolean"
        assert entries[variable].value is expected


@pytest.mark.parametrize(
    "selection_mode,oauth_mode,selection,oauth",
    [
        (False, "auto", False, False),
        ("auto", False, True, False),
        (True, "auto", True, True),
        ("auto", True, True, True),
    ],
)
def test_explicit_personal_modes_override_automatic_policy(
    selection_mode: PersonalConnectionsMode,
    oauth_mode: PersonalConnectionsMode,
    selection: bool,
    oauth: bool,
) -> None:
    config = build_app_config(
        OperatorSettings(
            _env_file=None,
            personal_connections_enabled=selection_mode,
            personal_connections_oauth_enabled=oauth_mode,
            personal_connections_identity_namespace="test:local",
            connector_store="sqlite",
            root_secret="secret",
        )
    )
    assert config.personal_connections.enabled is selection
    assert config.personal_connections.oauth_enabled is oauth


@pytest.mark.parametrize("namespace", [" ", " test:local", "test:", "authority"])
def test_automatic_selection_rejects_supplied_invalid_development_namespace(
    namespace: str,
) -> None:
    with pytest.raises(ValueError):
        build_app_config(
            OperatorSettings(
                _env_file=None, personal_connections_identity_namespace=namespace
            )
        )


def test_automatic_selection_rejects_unauthenticated_deployment() -> None:
    with pytest.raises(ValueError, match="authenticated"):
        build_app_config(
            OperatorSettings(
                _env_file=None,
                auth="none",
                personal_connections_identity_namespace="test:local",
            )
        )


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"personal_connections_enabled": False}, "personal connections to be enabled"),
        ({"connector_store": "inmemory"}, "persistent SQLite"),
        ({"connector_store_sqlite_path": ":memory:"}, "persistent SQLite"),
        ({"connector_store_sqlite_path": "file:db?mode=memory"}, "persistent SQLite"),
        ({"connector_store_sqlite_path": " "}, "persistent SQLite"),
        ({"root_secret": " \t"}, "configured encryption secret"),
    ],
)
def test_explicit_personal_oauth_rejects_invalid_prerequisites(
    overrides: dict[str, object], error: str
) -> None:
    values: dict[str, object] = {
        "personal_connections_identity_namespace": "test:local",
        "personal_connections_oauth_enabled": True,
        "connector_store": "sqlite",
        "root_secret": "secret",
    }
    values.update(overrides)
    with pytest.raises(ValidationError, match=error):
        build_app_config(OperatorSettings(_env_file=None, **values))


@pytest.mark.parametrize("auth", ["auth0", "entra", "google"])
def test_complete_production_authentication_automatically_enables_personal_features(
    auth: str,
) -> None:
    config = build_app_config(
        OperatorSettings(
            _env_file=None,
            profile="production",
            auth=auth,
            personal_connections_identity_namespace="deployment-authority",
            connector_store="sqlite",
            root_secret="production-policy-test-secret",
            oidc_domain="identity.example.com",
            oidc_tenant_id="tenant",
            oidc_client_id="client",
            oidc_client_secret="client-secret",
            oidc_audience="api",
            oidc_issuer_url="https://identity.example.com/",
            oidc_required_scopes=["api.read"],
        )
    )
    assert config.personal_connections.enabled is True
    assert config.personal_connections.oauth_enabled is True
