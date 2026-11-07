from pytest import MonkeyPatch

from umbod.config import AppConfig, OperatorSettings, build_app_config, load_app_config_without_env_file


def _config(monkeypatch: MonkeyPatch, **env: str) -> AppConfig:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return build_app_config(OperatorSettings(_env_file=None))


def test_connector_store_defaults_to_inmemory() -> None:
    settings = load_app_config_without_env_file()

    assert settings.connector_store.type == "inmemory"
    assert settings.connector_store.sqlite_path == ".data/umbod.sqlite3"


def test_connector_store_settings_use_environment_variable_names(monkeypatch: MonkeyPatch) -> None:
    settings = _config(
        monkeypatch,
        UMBOD_CONNECTOR_STORE="sqlite",
        UMBOD_CONNECTOR_STORE_SQLITE_PATH="/tmp/umbod.sqlite3",
    )

    assert settings.connector_store.type == "sqlite"
    assert settings.connector_store.sqlite_path == "/tmp/umbod.sqlite3"
