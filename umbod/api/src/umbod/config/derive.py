from umbod.config.app import AppConfig
from umbod.config.build import assemble_app_config
from umbod.config.operator import OperatorSettings
from umbod.config.validate import resolve_auth_recipe, validate_operator

_SECRET_FIELDS = (
    ("connector_security", "configuration_secret"),
    ("connector_security", "approval_state_key"),
    ("oidc", "client_secret"),
    ("oidc", "jwt_signing_key"),
    ("oauth_storage", "encryption_key"),
    ("mcp", "test_bearer_token"),
)


def build_app_config(operator: OperatorSettings) -> AppConfig:
    auth_recipe = resolve_auth_recipe(operator)
    validate_operator(operator, auth_recipe)
    return assemble_app_config(operator, auth_recipe)


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
