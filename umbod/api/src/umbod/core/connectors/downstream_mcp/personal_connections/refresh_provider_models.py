from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from ..personal_oauth_configuration import PersonalOAuthPolicy
from .authorization_models import PersonalOAuthGrant


class RefreshPersonalOAuth(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    grant: PersonalOAuthGrant
    policy: PersonalOAuthPolicy
    now: AwareDatetime
    timeout_seconds: float = Field(gt=0, le=20)


class PersonalOAuthRefreshDenied(ValueError):
    pass


class PersonalOAuthRefreshUncertain(ValueError):
    pass
