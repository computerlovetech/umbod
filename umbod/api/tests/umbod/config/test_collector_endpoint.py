import pytest
from pydantic import ValidationError

from umbod.config import AppConfig, OperatorSettings, build_app_config, inspect_app_config, safe_app_config_dump
from umbod.config.app import EndpointsConfig


def test_collector_url_is_unconfigured_by_default() -> None:
    config = build_app_config(OperatorSettings(_env_file=None))
    assert config.endpoints.collector_base_url == ""


def test_collector_url_environment_build_and_inspection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UMBOD_OTLP_PUBLIC_BASE_URL", "https://collector.example.test/otlp///")
    config = build_app_config(OperatorSettings(_env_file=None))
    assert config.endpoints.collector_base_url == "https://collector.example.test/otlp"
    entries = {
        entry.variable: entry
        for group in inspect_app_config(config).groups
        for entry in group.entries
    }
    entry = entries["UMBOD_OTLP_PUBLIC_BASE_URL"]
    assert entry.label == "Public collector base URL"
    assert entry.value == config.endpoints.collector_base_url
    assert safe_app_config_dump(config)["endpoints"]["collector_base_url"] == entry.value


@pytest.mark.parametrize(
    "url",
    [
        "", " ", "https://collector.example.test", "https://collector.example.test:4318/proxy/otlp/",
        "http://localhost:4318", "http://127.42.0.1:4318/proxy", "http://[::1]:4318/",
    ],
)
def test_collector_url_accepts_public_https_or_loopback_http(url: str) -> None:
    expected = url.rstrip("/") if url.strip() else ""
    assert EndpointsConfig(collector_base_url=url).collector_base_url == expected
    assert OperatorSettings(_env_file=None, otlp_public_base_url=url).otlp_public_base_url == expected


@pytest.mark.parametrize(
    "url",
    [
        "\n", "\t", "\x00", "/otlp", "//collector.test", "ftp://collector.test", "http://collector.test",
        "http://0.0.0.0:4318", "http://[::2]:4318", "https://",
        "https://user:password@collector.test", "https://collector.test?",
        "https://collector.test#", "https://collector.test?q=x", "https://collector.test/#x",
        "https://collector.test:bad", "https://collector.test:65536", "https://collector.test:",
        "https://collector.test:0", "https://[::1", "https://bad_host.test", "https://-bad.test",
        "https://collector.test/\npath", "https://collector.test/\tpath",
        "https://collector.test/\x00path", "https://collector.test/ path",
        "https://collector.test\\evil", "https://[::1]evil",
    ],
)
def test_collector_url_rejects_unsafe_or_malformed_values(url: str) -> None:
    with pytest.raises(ValidationError):
        EndpointsConfig(collector_base_url=url)
    with pytest.raises(ValidationError):
        OperatorSettings(_env_file=None, otlp_public_base_url=url)


def test_enabled_receiver_does_not_require_public_url() -> None:
    config = build_app_config(
        OperatorSettings(_env_file=None, otlp_enabled=True, otlp_bearer_token="ingestion-secret")
    )
    assert config.otlp_receiver.enabled is True
    assert config.endpoints.collector_base_url == ""
    assert AppConfig(otlp_receiver={"enabled": True}).endpoints.collector_base_url == ""
