from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ProtocolMethod(str, Enum):
    INITIALIZE = "initialize"
    LIST_TOOLS = "tools/list"


class ProtocolOutcome(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


class CompletedProtocolRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: ProtocolMethod
    outcome: ProtocolOutcome
    duration_seconds: float = Field(ge=0, allow_inf_nan=False)


class SuccessfulToolsList(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_count: int = Field(ge=0)
