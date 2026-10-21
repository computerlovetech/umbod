import json
from typing import Any

import pytest
from test_runtime import MemoryVault

from umbod_desktop.backward_compatibility.adapters.oauth import (
    KeychainLegacyAuthorizationImporter,
)
from umbod_desktop.backward_compatibility.contracts import LegacyAuthorization
from umbod_desktop.backward_compatibility.ports import LegacyAuthorizationImporter
from umbod_desktop.ports import CredentialVault


def test_legacy_authorization_preserves_serialization_and_refresh_metadata(monkeypatch: Any) -> None:
    monkeypatch.setattr("umbod_desktop.backward_compatibility.adapters.oauth.time.time", lambda: 1000)
    vault: CredentialVault = MemoryVault()
    original = json.dumps({
        "resource": "https://tools.example/mcp/", "client_id": "client",
        "access": "access-secret", "refresh": "refresh-secret", "expires": 1060,
    })
    vault.set("upstream:oauth:legacy", original)
    importer: LegacyAuthorizationImporter = KeychainLegacyAuthorizationImporter(vault)
    command = LegacyAuthorization(legacy_id="legacy", host_id="host", endpoint_url="https://tools.example/mcp")
    importer.import_authorization(command)
    imported = vault.get("python:oauth:host")
    assert imported is not None
    document = json.loads(imported)
    assert document["endpoint_url"] == command.endpoint_url
    assert document["client_info"]["client_id"] == "client"
    assert document["tokens"]["access_token"] == "access-secret"
    assert document["tokens"]["refresh_token"] == "refresh-secret"
    assert document["tokens"]["expires_in"] == 60
    assert document["expires_at"] == 1060
    assert vault.get("upstream:oauth:legacy") == original
    vault.set("python:oauth:host", "new-authorization")
    importer.import_authorization(command)
    assert vault.get("python:oauth:host") == "new-authorization"


@pytest.mark.parametrize("saved", [None, json.dumps({"resource": "https://other.example/mcp"})])
def test_legacy_authorization_rejects_missing_or_mismatched_resource(saved: str | None) -> None:
    vault: CredentialVault = MemoryVault()
    if saved is not None:
        vault.set("upstream:oauth:legacy", saved)
    importer: LegacyAuthorizationImporter = KeychainLegacyAuthorizationImporter(vault)
    with pytest.raises(ValueError):
        importer.import_authorization(LegacyAuthorization(
            legacy_id="legacy", host_id="host", endpoint_url="https://tools.example/mcp",
        ))
    assert vault.get("python:oauth:host") is None
