from pathlib import Path

import pytest

from umbod.mcp.auth.client_storage import MCPOAuthClientStorageFactory
from umbod.mcp.settings import OIDCOAuthStorageSettings

_TEST_OAUTH_STORAGE_ENCRYPTION_KEY = "uVIB4LyODL50BmxXDtJUL-QI1Mdue8HUZbk92i0X8Qc="
_OTHER_OAUTH_STORAGE_ENCRYPTION_KEY = "2eAPsDi2Kb3ogRxa75q6EbWrGkTz2KTK0RwyZgUjiRw="


def _storage_settings(directory: Path, encryption_key: str) -> OIDCOAuthStorageSettings:
    return OIDCOAuthStorageSettings(
        directory=str(directory), encryption_key=encryption_key, _env_file=None
    )


def test_factory_creates_storage_directory(tmp_path: Path) -> None:
    storage_dir = tmp_path / "fastmcp-oauth"

    MCPOAuthClientStorageFactory().create(
        _storage_settings(storage_dir, _TEST_OAUTH_STORAGE_ENCRYPTION_KEY)
    )

    assert storage_dir.is_dir()


@pytest.mark.asyncio
async def test_stored_value_persists_across_factory_instances(tmp_path: Path) -> None:
    storage_dir = tmp_path / "fastmcp-oauth"
    settings = _storage_settings(storage_dir, _TEST_OAUTH_STORAGE_ENCRYPTION_KEY)

    writer = MCPOAuthClientStorageFactory().create(settings)
    await writer.put("client-1", {"client_id": "client-1"}, collection="mcp-oauth-proxy-clients")

    reader = MCPOAuthClientStorageFactory().create(settings)
    stored = await reader.get("client-1", collection="mcp-oauth-proxy-clients")

    assert stored == {"client_id": "client-1"}


@pytest.mark.asyncio
async def test_value_written_with_a_different_key_is_treated_as_missing(tmp_path: Path) -> None:
    storage_dir = tmp_path / "fastmcp-oauth"

    writer = MCPOAuthClientStorageFactory().create(
        _storage_settings(storage_dir, _TEST_OAUTH_STORAGE_ENCRYPTION_KEY)
    )
    await writer.put("client-1", {"client_id": "client-1"}, collection="mcp-oauth-proxy-clients")

    reader = MCPOAuthClientStorageFactory().create(
        _storage_settings(storage_dir, _OTHER_OAUTH_STORAGE_ENCRYPTION_KEY)
    )
    stored = await reader.get("client-1", collection="mcp-oauth-proxy-clients")

    assert stored is None
