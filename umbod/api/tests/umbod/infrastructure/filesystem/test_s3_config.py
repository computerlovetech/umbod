import subprocess
import sys
from contextlib import AbstractAsyncContextManager
from typing import cast
from unittest.mock import Mock

import pytest
from pydantic import TypeAdapter, ValidationError

from umbod.infrastructure import ContentConfig, S3ContentConfig, create_content_driver
from umbod.infrastructure.filesystem.s3.edge import SDKClientProvider


def config_values() -> dict[str, object]:
    return {
        "type": "s3", "bucket": "test-bucket", "region": "us-east-1",
        "endpoint_url": "", "prefix": "", "addressing_style": "auto",
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("bucket", ""), ("bucket", "   "), ("bucket", "ab"), ("bucket", "ABC"),
        ("bucket", "s3://bucket"), ("bucket", "bucket/path"), ("bucket", "bucket name"),
        ("bucket", "bucket..name"), ("bucket", "127.0.0.1"), ("bucket", "xn--bucket"),
        ("bucket", "bucket--x-s3"), ("bucket", "arn:aws:s3:bucket"),
        ("region", ""), ("region", "   "), ("region", " us-east-1"),
        ("endpoint_url", "ftp://example.org"), ("endpoint_url", "https://user:pass@example.org"),
        ("endpoint_url", "https://example.org?secret=a"),
        ("endpoint_url", "https://example.org#secret"),
        ("endpoint_url", "https://example.org?"), ("endpoint_url", "https://example.org#"),
        ("endpoint_url", "https://example.org:invalid"), ("endpoint_url", "http://"),
        ("endpoint_url", "https://example.org\n"), ("endpoint_url", "https://example.org\\secret"),
        ("prefix", "/leading"), ("prefix", "trailing/"), ("prefix", "a//b"),
        ("prefix", "."), ("prefix", ".."), ("prefix", "a/../b"), ("prefix", "a/./b"),
        ("prefix", "a\\b"), ("prefix", "a\x00b"), ("prefix", "a\x7fb"),
        ("prefix", "a\x85b"),
        ("prefix", "x" * 992),
        ("addressing_style", "invalid"),
    ],
)
def test_invalid_s3_configuration_is_rejected(field: str, value: object) -> None:
    values = config_values()
    values[field] = value
    with pytest.raises(ValidationError):
        S3ContentConfig.model_validate(values)


@pytest.mark.parametrize("field", list(config_values()))
def test_all_s3_configuration_fields_are_required(field: str) -> None:
    values = config_values()
    del values[field]
    with pytest.raises(ValidationError):
        S3ContentConfig.model_validate(values)


@pytest.mark.parametrize("credential", ["access_key", "secret_key", "aws_access_key_id", "session_token"])
def test_s3_configuration_does_not_accept_credentials(credential: str) -> None:
    values = config_values()
    values[credential] = "secret"
    with pytest.raises(ValidationError):
        S3ContentConfig.model_validate(values)


def test_discriminated_union_roundtrip_and_factory_do_not_open_network() -> None:
    config = TypeAdapter(ContentConfig).validate_python(config_values())
    assert isinstance(config, S3ContentConfig)
    assert config.model_dump() == config_values()
    create_content_driver(config)


@pytest.mark.parametrize("style", ["auto", "virtual", "path"])
@pytest.mark.parametrize("endpoint", ["", "http://localhost:9000/storage"])
def test_sdk_provider_uses_signed_requests_default_chain_and_bounded_retries(
    monkeypatch: pytest.MonkeyPatch, endpoint: str, style: str,
) -> None:
    import aiobotocore.session

    session = Mock()
    session.create_client.return_value = cast(AbstractAsyncContextManager[object], Mock())
    get_session = Mock(return_value=session)
    monkeypatch.setattr(aiobotocore.session, "get_session", get_session)
    values = config_values()
    values.update(endpoint_url=endpoint, addressing_style=style)
    provider = SDKClientProvider(S3ContentConfig.model_validate(values))
    get_session.assert_not_called()
    provider()
    provider()
    assert get_session.call_count == 2
    args, options = session.create_client.call_args
    assert args == ("s3",)
    assert set(options) == (
        {"region_name", "config", "endpoint_url"} if endpoint else {"region_name", "config"}
    )
    assert options["region_name"] == "us-east-1"
    if endpoint:
        assert options["endpoint_url"] == endpoint
    sdk_config = options["config"]
    assert sdk_config.signature_version == "s3v4"
    assert sdk_config.s3 == {"addressing_style": style}
    assert sdk_config.retries == {"mode": "standard", "total_max_attempts": 3}
    assert sdk_config.connect_timeout == 10
    assert sdk_config.read_timeout == 60


def test_public_import_and_s3_construction_load_neither_sdk_nor_posix_drivers() -> None:
    code = """
import sys
from umbod.infrastructure import S3ContentConfig, create_content_driver
config = S3ContentConfig(type="s3", bucket="test-bucket", region="us-east-1", endpoint_url="", prefix="", addressing_style="auto")
create_content_driver(config)
assert not any(name.startswith(("aiobotocore", "botocore", "boto3")) for name in sys.modules)
assert "umbod.infrastructure.filesystem.objects" not in sys.modules
assert "umbod.infrastructure.filesystem.local_content" not in sys.modules
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
