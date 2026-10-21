import ipaddress
import json
from typing import Literal
from urllib.parse import SplitResult, unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr


MAX_BODY_BYTES = 1_048_576


def validated_url(value: str) -> SplitResult:
    if any(ord(character) <= 32 or ord(character) >= 127 for character in value):
        raise ValueError("Invalid URL")
    decoded = unquote(value)
    if any(ord(character) < 32 or ord(character) == 127 for character in decoded):
        raise ValueError("Invalid URL")
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or "?" in value
        or "#" in value
        or "\\" in value
        or parts.port == 0
        or "%" in parts.netloc
    ):
        raise ValueError("Invalid URL")
    try:
        address = ipaddress.ip_address(parts.hostname)
    except ValueError:
        return parts
    validated_public_address(str(address))
    return parts


def validated_public_address(literal: str) -> str:
    parsed = ipaddress.ip_address(literal)
    if (
        not parsed.is_global or parsed.is_reserved or parsed.is_multicast
        or parsed.is_unspecified or getattr(parsed, "ipv4_mapped", None) is not None
        or "%" in literal
    ):
        raise ValueError("Nonpublic address")
    return literal


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON member")
        result[key] = value
    return result


def parse_json(body: bytes) -> dict[str, object]:
    if len(body) > MAX_BODY_BYTES:
        raise ValueError("Response too large")
    result = json.loads(body, object_pairs_hook=unique_object)
    if not isinstance(result, dict):
        raise ValueError("Invalid JSON object")
    return result


class WireModel(BaseModel):
    model_config = ConfigDict(strict=True)


class ProtectedResource(WireModel):
    resource: str
    authorization_servers: list[str] = Field(min_length=1)


class AuthorizationServer(WireModel):
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str = ""
    code_challenge_methods_supported: list[str]
    grant_types_supported: list[str]
    response_types_supported: list[str]
    token_endpoint_auth_methods_supported: list[str] = Field(default_factory=lambda: ["client_secret_basic"])
    authorization_response_iss_parameter_supported: bool


class RegisteredClient(WireModel):
    client_id: str = Field(min_length=1, max_length=4096)
    redirect_uris: list[str]
    token_endpoint_auth_method: str = "client_secret_basic"
    grant_types: list[str]
    response_types: list[str]
    scope: str = ""


class TokenResponse(WireModel):
    access_token: SecretStr = Field(min_length=1)
    token_type: str
    refresh_token: SecretStr = Field(default=SecretStr(""))
    expires_in: int = Field(default=0, ge=0)
    scope: str = ""


class ProviderContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    issuer: str
    resource: str
    token_endpoint: str
    client_id: str
    redirect_uri: str
    authorization_url: str
    verifier_digest: str
    state_digest: str
    policy_revision: str = "legacy"
    requested_scopes: list[str] = Field(default_factory=list)
    client_mode: Literal["dynamic_public", "preconfigured_public", "preconfigured_confidential"] = "dynamic_public"
    token_endpoint_auth_method: Literal["none", "client_secret_basic", "client_secret_post"] = "none"
