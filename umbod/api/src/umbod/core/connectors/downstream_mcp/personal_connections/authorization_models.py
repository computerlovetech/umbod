import json
import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from ..personal_oauth_configuration.models import (
    OAuthClientId,
    OAuthIssuer,
    OAuthScopes,
)
from .models import Authorized, PersonalConnectionKey


class PersonalGrantModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExpiringPersonalToken(PersonalGrantModel):
    kind: Literal["expiring"] = "expiring"
    expires_at: AwareDatetime


class UnknownPersonalTokenLifetime(PersonalGrantModel):
    kind: Literal["unknown"] = "unknown"


class AbsentPersonalRefreshToken(PersonalGrantModel):
    kind: Literal["absent"] = "absent"


class PresentPersonalRefreshToken(PersonalGrantModel):
    kind: Literal["present"] = "present"
    token: SecretStr = Field(min_length=1, max_length=65536)

    @field_validator("token")
    @classmethod
    def validate_token(cls, value: SecretStr) -> SecretStr:
        if any(
            ord(character) < 32 or ord(character) == 127
            for character in value.get_secret_value()
        ):
            raise ValueError("Invalid refresh token")
        return value


class PersonalOAuthGrant(PersonalGrantModel):
    version: Literal[2]
    key: PersonalConnectionKey
    issuer: OAuthIssuer
    resource: OAuthIssuer
    client_id: OAuthClientId
    token_endpoint: OAuthIssuer
    redirect_uri: OAuthIssuer
    client_mode: Literal[
        "dynamic_public", "preconfigured_public", "preconfigured_confidential"
    ]
    token_endpoint_auth_method: Literal[
        "none", "client_secret_basic", "client_secret_post"
    ]
    requested_scopes: OAuthScopes
    granted_scopes: OAuthScopes
    configuration_revision: str = Field(min_length=1, max_length=128)
    issued_at: AwareDatetime
    lifetime: Annotated[
        ExpiringPersonalToken | UnknownPersonalTokenLifetime,
        Field(discriminator="kind"),
    ]
    access_token: SecretStr = Field(min_length=1, max_length=65536)
    token_type: Literal["Bearer"] = "Bearer"
    refresh_token: Annotated[
        AbsentPersonalRefreshToken | PresentPersonalRefreshToken,
        Field(discriminator="kind"),
    ]

    @field_validator("access_token")
    @classmethod
    def validate_access_token(cls, value: SecretStr) -> SecretStr:
        if not re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", value.get_secret_value()):
            raise ValueError("Invalid access token")
        return value

    @model_validator(mode="after")
    def validate_binding(self) -> "PersonalOAuthGrant":
        if not set(self.granted_scopes).issubset(self.requested_scopes):
            raise ValueError("Invalid granted scopes")
        if (
            isinstance(self.lifetime, ExpiringPersonalToken)
            and self.lifetime.expires_at < self.issued_at
        ):
            raise ValueError("Invalid token lifetime")
        expected_methods = (
            {"client_secret_basic", "client_secret_post"}
            if self.client_mode == "preconfigured_confidential"
            else {"none"}
        )
        if self.token_endpoint_auth_method not in expected_methods:
            raise ValueError("Invalid client authentication binding")
        return self


def _serialize_grant_value(value: object) -> str:
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError("Unsupported personal grant value")


def authorize_personal_grant(grant: PersonalOAuthGrant) -> Authorized:
    return Authorized(
        authorization=SecretStr(
            json.dumps(grant.model_dump(mode="python"), default=_serialize_grant_value)
        )
    )
