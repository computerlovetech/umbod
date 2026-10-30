from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, AfterValidator, field_validator


def require_nonblank_label(value: str) -> str:
    if not value.strip():
        raise ValueError("Group label must not be blank")
    return value.strip()


GroupLabel = Annotated[str, Field(max_length=200), AfterValidator(require_nonblank_label)]
GroupDescription = Annotated[str, Field(max_length=2000)]
GroupRevision = Annotated[int, Field(strict=True, gt=0)]


class GroupIdentifier(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    group_id: str


class Group(GroupIdentifier):
    label: str
    description: GroupDescription
    revision: GroupRevision


class RegisterGroup(GroupIdentifier):
    @field_validator("group_id")
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Group ID must not be empty")
        return value


class RegisterGroupMetadata(RegisterGroup):
    label: GroupLabel
    description: GroupDescription


class UpdateGroupMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    label: GroupLabel
    description: GroupDescription
    expected_revision: GroupRevision


class GroupInUse(Exception):
    pass


class GroupNotFound(Exception):
    pass


class GroupRevisionConflict(Exception):
    pass
