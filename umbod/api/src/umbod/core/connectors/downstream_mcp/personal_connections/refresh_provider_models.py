from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from ..personal_oauth_configuration import PersonalOAuthPolicy
from .authorization_models import PersonalOAuthGrant
from .oauth_failure_models import OAuthEvidenceError, OAuthFailureReason, OAuthFailureStage


class RefreshPersonalOAuth(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    grant: PersonalOAuthGrant
    policy: PersonalOAuthPolicy
    now: AwareDatetime
    timeout_seconds: float = Field(gt=0, le=20)


class PersonalOAuthRefreshDenied(OAuthEvidenceError):
    stage: OAuthFailureStage = "refresh"
    reason: OAuthFailureReason = "provider_rejected"
    message = "Personal OAuth refresh denied"


class PersonalOAuthRefreshUncertain(OAuthEvidenceError):
    stage: OAuthFailureStage = "refresh"
    message = "Personal OAuth refresh outcome uncertain"
