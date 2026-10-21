from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from .models import PersonalConnectionKey


class AuthorizationHealthModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PersonalAuthorizationHealthQuery(AuthorizationHealthModel):
    key: PersonalConnectionKey
    now: AwareDatetime


class RejectPersonalAuthorization(AuthorizationHealthModel):
    key: PersonalConnectionKey
    expected_connection_revision: str = Field(min_length=1)


class NotAuthorized(AuthorizationHealthModel):
    state: Literal["not_authorized"] = "not_authorized"


class LocallyAuthorized(AuthorizationHealthModel):
    state: Literal["authorized"] = "authorized"
    expires_at: AwareDatetime
    refresh_supported: bool


class ExpiredAuthorization(AuthorizationHealthModel):
    state: Literal["expired"] = "expired"
    expires_at: AwareDatetime
    refresh_supported: bool


class UnsupportedAuthorization(AuthorizationHealthModel):
    state: Literal["unsupported"] = "unsupported"


class ReconnectRequired(AuthorizationHealthModel):
    state: Literal["reconnect_required"] = "reconnect_required"
    reason: Literal["provider_rejected", "refresh_uncertain", "refresh_denied"] = "provider_rejected"


class RefreshingAuthorization(AuthorizationHealthModel):
    state: Literal["refreshing"] = "refreshing"
    deadline: AwareDatetime


PersonalAuthorizationHealth = Annotated[
    NotAuthorized | LocallyAuthorized | ExpiredAuthorization | UnsupportedAuthorization | ReconnectRequired | RefreshingAuthorization,
    Field(discriminator="state"),
]


class PersonalAuthorizationHealthUnavailable(ValueError):
    pass
