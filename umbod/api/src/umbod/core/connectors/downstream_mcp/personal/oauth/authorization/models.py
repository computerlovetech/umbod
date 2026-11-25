from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr, model_validator

from ..configuration import PersonalOAuthPolicy, legacy_personal_oauth_policy

from ..failures import OAuthEvidenceError, OAuthFailureReason
from ...connections import Authorized, PersonalConnectionKey
from ..callback import CallbackBinding, CallbackIssuer, CallbackRoute, LegacyGenericBinding


class PersonalOAuthModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PreparePersonalOAuth(PersonalOAuthModel):
    connector_id: str = ""
    endpoint_url: str = Field(min_length=1)
    redirect_uri: str = Field(min_length=1)
    state: SecretStr
    code_verifier: SecretStr
    policy: PersonalOAuthPolicy = Field(default_factory=legacy_personal_oauth_policy)

    @model_validator(mode="after")
    def validate_connector_binding(self) -> "PreparePersonalOAuth":
        if self.policy.client.kind == "dynamic_confidential" and not self.connector_id.strip():
            raise ValueError("Connector identifier required")
        return self


class PreparedPersonalOAuth(PersonalOAuthModel):
    authorization_url: SecretStr
    context: SecretStr
    callback_binding: CallbackBinding = Field(default_factory=lambda: LegacyGenericBinding(kind="legacy_generic"))


class PersonalOAuthAttemptQuery(PersonalOAuthModel):
    key: PersonalConnectionKey
    attempt_id: str = Field(min_length=1, max_length=128)
    now: AwareDatetime


class ReservePersonalOAuthAttempt(PersonalOAuthModel):
    key: PersonalConnectionKey
    attempt_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    expected_revision: str = Field(min_length=1)
    definition_fingerprint: str = Field(min_length=1)
    endpoint_url: str = Field(min_length=1)
    group_ids: tuple[str, ...]
    preparation: PreparePersonalOAuth
    created_at: AwareDatetime
    expires_at: AwareDatetime


class PersonalOAuthAttemptView(PersonalOAuthModel):
    attempt_id: str
    status: Literal["preparing", "pending", "exchanging", "completed", "cancelled", "failed", "expired"]
    expires_at: AwareDatetime


class PublishPersonalOAuthAttempt(PersonalOAuthModel):
    query: PersonalOAuthAttemptQuery
    prepared: PreparedPersonalOAuth


class FinishCallback(PersonalOAuthModel):
    state: SecretStr
    code: SecretStr
    issuer: CallbackIssuer
    error: str
    scope: str
    route: CallbackRoute


class ClaimPersonalOAuthAttempt(PersonalOAuthModel):
    route: CallbackRoute
    issuer: CallbackIssuer
    state: SecretStr
    claim_id: str = Field(min_length=1)
    now: AwareDatetime


class ClaimedPersonalOAuthAttempt(PersonalOAuthModel):
    query: PersonalOAuthAttemptQuery
    claim_id: str
    preparation: PreparePersonalOAuth
    prepared: PreparedPersonalOAuth


class ExchangePersonalOAuth(PersonalOAuthModel):
    attempt: ClaimedPersonalOAuthAttempt
    code: SecretStr
    issuer: CallbackIssuer
    route: CallbackRoute


class CompletePersonalOAuthAttempt(PersonalOAuthModel):
    query: PersonalOAuthAttemptQuery
    claim_id: str
    authorization: Authorized


class FailPersonalOAuthAttempt(PersonalOAuthModel):
    query: PersonalOAuthAttemptQuery
    claim_id: str


class PersonalOAuthStartResult(PersonalOAuthModel):
    attempt: PersonalOAuthAttemptView
    authorization_url: SecretStr


class PersonalOAuthUnavailable(ValueError):
    pass


class PersonalOAuthConflict(ValueError):
    pass


class PersonalOAuthProviderUnsupported(OAuthEvidenceError):
    reason: OAuthFailureReason = "invalid_response"
    message = "Personal OAuth provider is unsupported"


class PersonalOAuthProviderFailure(OAuthEvidenceError):
    pass
