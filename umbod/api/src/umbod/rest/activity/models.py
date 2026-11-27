from pydantic import BaseModel, ConfigDict, Field, field_validator

from umbod.core.activity.models import ActivityOverview, SessionPage, SessionReport
from umbod.core.usage import UsageOwner


class ActivityWindowQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: int = Field(default=7, ge=7, le=30)

    @field_validator("days")
    @classmethod
    def supported_window(cls, value: int) -> int:
        if value not in (7, 30):
            raise ValueError("Choose seven or thirty days")
        return value


class ActivityIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    owner: UsageOwner
    identity_key: str


class ActivityOverviewResponse(ActivityOverview):
    identity_key: str


class ActivitySessionsResponse(SessionPage):
    identity_key: str


class ActivitySessionResponse(SessionReport):
    identity_key: str
