from pydantic import ValidationError

from umbod.config.app import AppConfig
from umbod.config.build import assemble_app_config
from umbod.config.operator import OperatorSettings
from umbod.config.personal_connection_policy import normalize_personal_connections_operator
from umbod.config.server_settings import ServerRootSettings
from umbod.config.validate import resolve_auth_recipe, validate_operator

_SERVER_ROOT_SECRET_ERROR = (
    "UMBOD_ROOT_SECRET is required and must not be blank to start API or MCP servers. "
    "Configure a persistent secret before starting the server."
)

_SECRET_FIELDS = (
    ("connector_security", "configuration_secret"),
    ("connector_security", "approval_state_key"),
    ("oidc", "client_secret"),
    ("oidc", "jwt_signing_key"),
    ("oauth_storage", "encryption_key"),
    ("mcp", "test_bearer_token"),
    ("otlp_receiver", "bearer_token"),
)


def build_app_config(operator: OperatorSettings) -> AppConfig:
    auth_recipe = resolve_auth_recipe(operator)
    operator = normalize_personal_connections_operator(operator, auth_recipe)
    validate_operator(operator, auth_recipe)
    return assemble_app_config(operator, auth_recipe)


def load_server_app_config(env_file: str) -> AppConfig:
    try:
        root_settings = ServerRootSettings(_env_file=env_file)
    except ValidationError:
        raise ValueError(_SERVER_ROOT_SECRET_ERROR) from None
    if not root_settings.root_secret.strip():
        raise ValueError(_SERVER_ROOT_SECRET_ERROR)
    operator = OperatorSettings(_env_file=env_file)
    if not operator.root_secret.strip():
        raise ValueError(_SERVER_ROOT_SECRET_ERROR)
    return build_app_config(operator)


def load_app_config(env_file: str) -> AppConfig:
    return build_app_config(OperatorSettings(_env_file=env_file))


def load_app_config_without_env_file() -> AppConfig:
    return build_app_config(OperatorSettings(_env_file=None))


def redact_app_config(config: AppConfig) -> dict:
    data = config.model_dump()
    for section, field in _SECRET_FIELDS:
        value = data.get(section, {}).get(field)
        if isinstance(value, str) and value:
            data[section][field] = "***"
    return data
