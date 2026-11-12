from pydantic import BaseModel, ConfigDict, Field, field_validator

from umbod.core.usage.models import OwnerId, UsageSummary


class PersonalUsageRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    days: int = Field(default=7, ge=7, le=30)

    @field_validator('days')
    @classmethod
    def supported_window(cls, value: int) -> int:
        if value not in (7, 30):
            raise ValueError('Choose seven or thirty days')
        return value


class PersonalUsageIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')

    owner_id: OwnerId
    identity_key: str


class PersonalUsageResponse(UsageSummary):
    identity_key: str
