import pytest

from umbod.config import load_app_config_without_env_file, safe_app_config_dump
from umbod.config.system_settings import (
    ConfiguredProviderGroupMappingsDefaults,
    parse_provider_group_mappings,
)
from umbod.core.system_settings import (
    SettingsNotConfigured,
    SettingsSource,
    SettingsStorageUnavailable,
)
from umbod.core.system_settings.provider_group_mappings import ProviderGroupMapping

_ENV = "UMBOD_PROVIDER_GROUP_OVERRIDES"


@pytest.mark.asyncio
async def test_deployment_defaults_capture_startup_input_verbatim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        _ENV,
        '[{"external_value":" Staff ","group_id":"unregistered"}]',
    )
    config = load_app_config_without_env_file()
    monkeypatch.setenv(_ENV, "[]")

    defaults = await ConfiguredProviderGroupMappingsDefaults(config).read()
    assert defaults is not SettingsNotConfigured.UNSET
    assert defaults.source is SettingsSource.DEPLOYMENT_DEFAULT
    assert defaults.mappings == (
        ProviderGroupMapping(
            external_value=" Staff ",
            group_id="unregistered",
        ),
    )


@pytest.mark.asyncio
async def test_unset_deployment_configuration_is_distinct_from_an_empty_array(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(_ENV, raising=False)
    absent = load_app_config_without_env_file()
    monkeypatch.setenv(_ENV, "[]")
    empty = load_app_config_without_env_file()

    assert (
        await ConfiguredProviderGroupMappingsDefaults(absent).read()
        is SettingsNotConfigured.UNSET
    )
    configured_empty = await ConfiguredProviderGroupMappingsDefaults(empty).read()
    assert configured_empty is not SettingsNotConfigured.UNSET
    assert configured_empty.mappings == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw",
    [
        "",
        "  ",
        "null",
        "{",
        "{}",
        "[null]",
        '[{"secret-invalid":"secret-invalid"}]',
        '[{"external_value":"v"}]',
        '[{"external_value":"v","group_id":null}]',
        '[{"external_value":"v","group_id":" \\t "}]',
        '[{"external_value":"v","group_id":1}]',
        '[{"external_value":"v","group_id":"g","issuer":"i"}]',
        '[{"external_value":"v","group_id":"g","claim":"c"}]',
        '[{"external_value":"v","group_id":"g"},'
        '{"external_value":"v","group_id":"g"}]',
    ],
)
async def test_malformed_deployment_data_only_fails_when_selected(
    monkeypatch: pytest.MonkeyPatch,
    raw: str,
) -> None:
    monkeypatch.setenv(_ENV, raw)
    config = load_app_config_without_env_file()

    assert "provider_group_overrides" not in safe_app_config_dump(config)
    assert "provider_group_overrides" not in repr(config)
    with pytest.raises(
        SettingsStorageUnavailable, match="^System settings storage is unavailable$"
    ):
        await ConfiguredProviderGroupMappingsDefaults(config).read()


def test_multiple_distinct_targets_are_allowed_for_one_claim_value() -> None:
    rules = parse_provider_group_mappings(
        '[{"external_value":"v","group_id":"team"},'
        '{"external_value":"v","group_id":"other"}]',
    )

    assert tuple(rule.group_id for rule in rules) == ("team", "other")
