import re
from typing import Annotated, Literal
from urllib.parse import unquote, urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    TypeAdapter,
    field_validator,
)


class OAuthConfigurationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def validate_scope_token(value: str) -> str:
    if not re.fullmatch(r"[\x21\x23-\x5b\x5d-\x7e]+", value):
        raise ValueError("Invalid OAuth scope token")
    return value


def canonical_scope_set(value: tuple[str, ...]) -> tuple[str, ...]:
    if len(set(value)) != len(value) or len(" ".join(value)) > 4096:
        raise ValueError("Invalid OAuth scope set")
    return tuple(sorted(value))


OAuthScope = Annotated[
    str, Field(min_length=1, max_length=256), AfterValidator(validate_scope_token)
]
OAuthScopes = Annotated[
    tuple[OAuthScope, ...], Field(max_length=64), AfterValidator(canonical_scope_set)
]
_SCOPE_ADAPTER = TypeAdapter(OAuthScopes)


def parse_oauth_scopes(value: str) -> tuple[str, ...]:
    if not value:
        return ()
    return _SCOPE_ADAPTER.validate_python(tuple(value.split(" ")))


def validate_client_identifier(value: str) -> str:
    if not value.strip() or any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("Invalid OAuth client identifier")
    return value


OAuthClientId = Annotated[
    str, Field(min_length=1, max_length=4096), AfterValidator(validate_client_identifier)
]


def validate_configured_issuer(value: str) -> str:
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
        or "%" in parts.netloc
        or any(ord(character) <= 32 or ord(character) >= 127 for character in value)
        or any(ord(character) < 32 or ord(character) == 127 for character in unquote(value))
        or parts.port == 0
    ):
        raise ValueError("Invalid configured OAuth issuer")
    return value


OAuthIssuer = Annotated[
    str, Field(min_length=1, max_length=4096), AfterValidator(validate_configured_issuer)
]


class DynamicPublicOAuthClient(OAuthConfigurationModel):
    kind: Literal["dynamic_public"] = "dynamic_public"


class PreconfiguredPublicOAuthClient(OAuthConfigurationModel):
    kind: Literal["preconfigured_public"] = "preconfigured_public"
    issuer_url: OAuthIssuer
    client_id: OAuthClientId


class PreconfiguredConfidentialOAuthClient(OAuthConfigurationModel):
    kind: Literal["preconfigured_confidential"] = "preconfigured_confidential"
    issuer_url: OAuthIssuer
    client_id: OAuthClientId
    token_endpoint_auth_method: Literal["client_secret_basic", "client_secret_post"]
    client_secret: SecretStr = Field(min_length=1, max_length=4096)

    @field_validator("client_secret")
    @classmethod
    def validate_client_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if not secret.strip() or any(ord(character) < 32 or ord(character) == 127 for character in secret):
            raise ValueError("Invalid OAuth client secret")
        return value


PersonalOAuthClient = Annotated[
    DynamicPublicOAuthClient | PreconfiguredPublicOAuthClient | PreconfiguredConfidentialOAuthClient,
    Field(discriminator="kind"),
]


class PersonalOAuthSettings(OAuthConfigurationModel):
    requested_scopes: OAuthScopes
    client: PersonalOAuthClient


class PersonalOAuthPolicy(PersonalOAuthSettings):
    revision: str = Field(min_length=1, max_length=128)


def legacy_personal_oauth_settings() -> PersonalOAuthSettings:
    return PersonalOAuthSettings(requested_scopes=(), client=DynamicPublicOAuthClient())


def legacy_personal_oauth_policy() -> PersonalOAuthPolicy:
    return PersonalOAuthPolicy(
        revision="legacy", requested_scopes=(), client=DynamicPublicOAuthClient()
    )


class PersonalOAuthConfiguration(OAuthConfigurationModel):
    connector_id: str = Field(min_length=1)
    policy: PersonalOAuthPolicy


class PersonalOAuthConfigurationQuery(OAuthConfigurationModel):
    connector_id: str = Field(min_length=1)


class ReplacePersonalOAuthConfiguration(OAuthConfigurationModel):
    connector_id: str = Field(min_length=1)
    expected_revision: str = Field(min_length=1, max_length=128)
    settings: PersonalOAuthSettings


class PersonalOAuthConfigurationUnavailable(ValueError):
    pass


class PersonalOAuthConfigurationConflict(ValueError):
    pass
