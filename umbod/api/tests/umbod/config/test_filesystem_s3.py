import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from umbod.config import (
    AppConfig,
    FilesystemContentConfig,
    InMemoryFilesystemContentConfig,
    LocalFilesystemContentConfig,
    OperatorSettings,
    S3FilesystemContentConfig,
    build_app_config,
    redact_app_config,
    safe_app_config_dump,
)
from umbod.infrastructure import ContentConfig, S3ContentConfig


@pytest.fixture
def s3_payload() -> dict[str, str]:
    return {
        "type": "s3",
        "bucket": "umbod-content",
        "region": "us-east-1",
        "endpoint_url": "",
        "prefix": "",
        "addressing_style": "auto",
    }


@pytest.mark.parametrize("endpoint,prefix,style", [
    ("", "", "auto"),
    ("http://minio:9000", "umbod/content", "path"),
    ("https://s3.eu-west-1.amazonaws.com", "content", "virtual"),
])
def test_environment_derives_exact_s3_payload_and_roundtrips_discriminator(
    monkeypatch: pytest.MonkeyPatch, s3_payload: dict[str, str],
    endpoint: str, prefix: str, style: str,
) -> None:
    s3_payload.update(endpoint_url=endpoint, prefix=prefix, addressing_style=style)
    monkeypatch.setenv("UMBOD_FILESYSTEM_CONTENT_BACKEND", "s3")
    for field, value in s3_payload.items():
        if field != "type":
            monkeypatch.setenv(f"UMBOD_FILESYSTEM_S3_{field.upper()}", value)

    config = build_app_config(OperatorSettings(_env_file=None))

    assert isinstance(config.filesystem.content, S3FilesystemContentConfig)
    assert config.filesystem.content.model_dump() == s3_payload
    restored = TypeAdapter(FilesystemContentConfig).validate_json(json.dumps(s3_payload))
    assert restored == config.filesystem.content
    infrastructure = TypeAdapter(ContentConfig).validate_python(restored.model_dump())
    assert isinstance(infrastructure, S3ContentConfig)
    assert infrastructure.model_dump() == s3_payload
    assert AppConfig.model_validate_json(config.model_dump_json()) == config


def test_default_operator_local_and_programmatic_inmemory_are_preserved() -> None:
    operator_config = build_app_config(OperatorSettings(_env_file=None))

    assert operator_config.filesystem.content == LocalFilesystemContentConfig(
        directory=Path(".data/filesystem-content")
    )
    assert AppConfig().filesystem.content == InMemoryFilesystemContentConfig()


@pytest.mark.parametrize("field,value", [
    ("bucket", ""), ("bucket", "Uppercase"), ("bucket", "ab"),
    ("bucket", "192.168.0.1"), ("bucket", "a..b"), ("bucket", "xn--bucket"),
    ("bucket", "bucket--x-s3"), ("bucket", "bucket-s3alias"),
    ("bucket", "bucket.-name"), ("bucket", "bucket-.name"),
    ("region", ""), ("region", " \t"), ("region", " us-east-1"),
    ("endpoint_url", "ftp://minio"), ("endpoint_url", "http://"),
    ("endpoint_url", "http://user:password@minio"),
    ("endpoint_url", "https://minio?query=1"),
    ("endpoint_url", "https://minio#fragment"),
    ("endpoint_url", "https://minio?"), ("endpoint_url", "https://minio\n"),
    ("endpoint_url", "https://minio:invalid"), ("endpoint_url", "https://minio:99999"),
    ("endpoint_url", "https://minio\\path"), ("endpoint_url", "https://minio/\x80"),
    ("prefix", "/content"), ("prefix", "content/"), ("prefix", "a//b"),
    ("prefix", "a/./b"), ("prefix", "a/../b"), ("prefix", "a\\b"),
    ("prefix", "a\x00b"), ("prefix", "a\x7fb"), ("prefix", "a\x80b"), ("prefix", "a" * 992),
    ("addressing_style", "unknown"),
])
def test_runtime_s3_rejects_invalid_configuration(
    s3_payload: dict[str, str], field: str, value: str,
) -> None:
    s3_payload[field] = value

    with pytest.raises(ValidationError):
        AppConfig(filesystem={"content": s3_payload})


@pytest.mark.parametrize("field", [
    "bucket", "region", "endpoint_url", "prefix", "addressing_style",
])
def test_runtime_s3_requires_every_storage_field(
    s3_payload: dict[str, str], field: str,
) -> None:
    del s3_payload[field]

    with pytest.raises(ValidationError, match=field):
        TypeAdapter(FilesystemContentConfig).validate_python(s3_payload)


@pytest.mark.parametrize("field,value", [
    ("BUCKET", ""), ("REGION", " "),
    ("ENDPOINT_URL", "http://user:password@minio"), ("PREFIX", "../content"),
])
def test_selected_s3_environment_is_validated_before_runtime(
    monkeypatch: pytest.MonkeyPatch, field: str, value: str,
) -> None:
    monkeypatch.setenv("UMBOD_FILESYSTEM_CONTENT_BACKEND", "s3")
    monkeypatch.setenv("UMBOD_FILESYSTEM_S3_BUCKET", "umbod-content")
    monkeypatch.setenv(f"UMBOD_FILESYSTEM_S3_{field}", value)

    with pytest.raises(ValidationError):
        build_app_config(OperatorSettings(_env_file=None))


@pytest.mark.parametrize("field,value", [
    ("BUCKET", "umbod-content"), ("ENDPOINT_URL", "http://minio:9000"),
    ("PREFIX", "content"), ("REGION", "eu-west-1"), ("ADDRESSING_STYLE", "path"),
])
def test_local_backend_rejects_nondefault_s3_settings(
    monkeypatch: pytest.MonkeyPatch, field: str, value: str,
) -> None:
    monkeypatch.setenv(f"UMBOD_FILESYSTEM_S3_{field}", value)

    with pytest.raises(ValidationError, match="S3 settings require"):
        OperatorSettings(_env_file=None)


def test_s3_backend_requires_bucket_without_changing_local_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UMBOD_FILESYSTEM_CONTENT_BACKEND", "s3")
    monkeypatch.delenv("UMBOD_FILESYSTEM_S3_BUCKET", raising=False)

    with pytest.raises(ValidationError, match="bucket"):
        build_app_config(OperatorSettings(_env_file=None))


def test_s3_backend_rejects_explicit_local_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UMBOD_FILESYSTEM_CONTENT_BACKEND", "s3")
    monkeypatch.setenv("UMBOD_FILESYSTEM_CONTENT_DIRECTORY", "/content")
    monkeypatch.setenv("UMBOD_FILESYSTEM_S3_BUCKET", "umbod-content")

    with pytest.raises(ValidationError, match="local content directory"):
        OperatorSettings(_env_file=None)


def test_unknown_backend_does_not_fall_back_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UMBOD_FILESYSTEM_CONTENT_BACKEND", "unknown")

    with pytest.raises(ValidationError, match="filesystem_content_backend"):
        OperatorSettings(_env_file=None)


@pytest.mark.parametrize("credential", ["aws_access_key_id", "aws_secret_access_key", "aws_session_token"])
def test_runtime_s3_forbids_credential_fields(
    s3_payload: dict[str, str], credential: str,
) -> None:
    s3_payload[credential] = "credential-value"

    with pytest.raises(ValidationError, match="extra_forbidden"):
        TypeAdapter(FilesystemContentConfig).validate_python(s3_payload)


def test_aws_provider_credentials_never_enter_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UMBOD_FILESYSTEM_CONTENT_BACKEND", "s3")
    monkeypatch.setenv("UMBOD_FILESYSTEM_S3_BUCKET", "umbod-content")
    credentials = {
        "AWS_ACCESS_KEY_ID": "provider-access-key",
        "AWS_SECRET_ACCESS_KEY": "provider-secret-key",
        "AWS_SESSION_TOKEN": "provider-session-token",
        "AWS_PROFILE": "provider-profile",
    }
    for name, value in credentials.items():
        monkeypatch.setenv(name, value)

    config = build_app_config(OperatorSettings(_env_file=None))

    for payload in (config.model_dump(mode="json"), redact_app_config(config), safe_app_config_dump(config)):
        serialized = json.dumps(payload)
        assert all(value not in serialized for value in credentials.values())
        assert all(name.lower() not in serialized.lower() for name in credentials)
