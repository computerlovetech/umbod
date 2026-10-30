from typing import Literal, Optional, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

class PlannedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class PatchNodeRequest(PlannedRequest):
    name: Optional[str] = Field(default=None, min_length=1)
    parent_id: Optional[UUID] = Field(default=None, strict=False)

    @model_validator(mode="after")
    def require_changes(self) -> Self:
        if not self.model_fields_set or any(
            getattr(self, field) is None for field in self.model_fields_set
        ):
            raise ValueError("Provide at least one non-null change.")
        return self


class PlannedErrorDetail(BaseModel):
    code: Literal["filesystem_not_implemented"]
    message: str


class PlannedErrorResponse(BaseModel):
    detail: PlannedErrorDetail
