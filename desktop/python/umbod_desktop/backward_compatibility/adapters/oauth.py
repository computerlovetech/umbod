import json
import time

from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth import (
    AuthorizationDocument,
)

from ...ports import CredentialVault
from ..contracts import LegacyAuthorization


class KeychainLegacyAuthorizationImporter:
    def __init__(self, vault: CredentialVault) -> None:
        self.vault = vault

    def import_authorization(self, authorization: LegacyAuthorization) -> None:
        reference = f"python:oauth:{authorization.host_id}"
        if self.vault.get(reference) is not None:
            return
        raw = self.vault.get(f"upstream:oauth:{authorization.legacy_id}")
        if raw is None:
            raise ValueError("Legacy OAuth credential is missing")
        saved = json.loads(raw)
        if saved["resource"].rstrip("/") != authorization.endpoint_url.rstrip("/"):
            raise ValueError("OAuth resource does not match")
        document = AuthorizationDocument(
            endpoint_url=authorization.endpoint_url,
            client_info=OAuthClientInformationFull(client_id=saved["client_id"]),
            tokens=OAuthToken(
                access_token=saved["access"],
                token_type="Bearer",
                refresh_token=saved.get("refresh"),
                expires_in=max(0, int(saved["expires"] - time.time())),
            ),
            expires_at=saved["expires"],
        )
        self.vault.set(reference, document.model_dump_json())
