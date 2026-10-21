from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr

from ..personal_oauth_configuration import PersonalOAuthPolicy, legacy_personal_oauth_policy

from .models import Authorized, PersonalConnectionKey


class PersonalOAuthModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PreparePersonalOAuth(PersonalOAuthModel):
    endpoint_url: str = Field(min_length=1)
    redirect_uri: str = Field(min_length=1)
    state: SecretStr
    code_verifier: SecretStr
    policy: PersonalOAuthPolicy = Field(default_factory=legacy_personal_oauth_policy)


class PreparedPersonalOAuth(PersonalOAuthModel):
    authorization_url: SecretStr
    context: SecretStr


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


class ClaimPersonalOAuthAttempt(PersonalOAuthModel):
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
    issuer: str


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


class PersonalOAuthProviderUnsupported(ValueError):
    pass


class PersonalOAuthProviderFailure(ValueError):
    pass
