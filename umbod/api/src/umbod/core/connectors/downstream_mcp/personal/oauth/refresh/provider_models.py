from pydantic import AwareDatetime, ConfigDict, Field

from umbod.proxies import Model

from ..configuration import PersonalOAuthPolicy
from ..grants import PersonalOAuthGrant
from ..failures import OAuthEvidenceError, OAuthFailureReason, OAuthFailureStage


class RefreshPersonalOAuth(Model):
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
