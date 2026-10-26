from pydantic import BaseModel, ConfigDict, field_validator


class Group(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    group_id: str


class RegisterGroup(Group):
    @field_validator("group_id")
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Group ID must not be empty")
        return value


class GroupInUse(Exception):
    pass
