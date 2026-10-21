from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from ..personal_oauth_configuration import PersonalOAuthPolicy
from .authorization_models import PersonalOAuthGrant
from .models import Authorized, PersonalConnectionKey


class RefreshModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReservePersonalRefresh(RefreshModel):
    key: PersonalConnectionKey
    group_ids: tuple[str, ...]
    claim_id: str = Field(min_length=1, max_length=128)
    now: AwareDatetime


class PersonalRefreshClaim(RefreshModel):
    key: PersonalConnectionKey
    claim_id: str = Field(min_length=1, max_length=128)
    group_ids: tuple[str, ...]
    expected_revision: str = Field(min_length=1)
    credential_fingerprint: str = Field(pattern="^[0-9a-f]{64}$")
    definition_fingerprint: str = Field(pattern="^[0-9a-f]{64}$")
    policy: PersonalOAuthPolicy
    grant: PersonalOAuthGrant
    deadline: AwareDatetime
    status: Literal["preparing", "exchanging", "refresh_uncertain", "refresh_denied"]


class PersonalRefreshCommand(RefreshModel):
    key: PersonalConnectionKey
    claim_id: str = Field(min_length=1, max_length=128)
    now: AwareDatetime


class CompletePersonalRefresh(PersonalRefreshCommand):
    authorization: Authorized


class FailPersonalRefresh(PersonalRefreshCommand):
    reason: Literal["refresh_uncertain", "refresh_denied"]


class PersonalRefreshConflict(ValueError):
    pass


class PersonalRefreshUnsupported(ValueError):
    pass


class PersonalRefreshChanged(ValueError):
    pass


class PersonalRefreshReconnectRequired(ValueError):
    pass


class PersonalRefreshUnavailable(ValueError):
    pass
