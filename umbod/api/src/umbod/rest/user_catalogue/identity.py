import hashlib
import json
from collections.abc import Mapping

from umbod.config import AppConfig


def catalogue_identity_key(claims: Mapping[str, object]) -> str:
    subject = claims.get("sub")
    identity = (
        {"iss": claims.get("iss", ""), "sub": subject}
        if isinstance(subject, str) and subject.strip()
        else {key: value for key, value in claims.items() if key in (
            "iss", "oid", "tid", "email", "client_id", "azp",
        )}
    )
    return hashlib.sha256(json.dumps(
        identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode()).hexdigest()


def local_catalogue_identity_enabled(settings: AppConfig) -> bool:
    return (
        settings.runtime.profile == "local"
        and settings.runtime.auth == "dev"
        and settings.admin_authentication.mode == "simulation"
        and settings.admin_authentication.environment == "development"
        and bool(settings.admin_authentication.simulated_user_id.strip())
    )
