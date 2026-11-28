from enum import Enum

from pydantic import ConfigDict, Field

from umbod.proxies import Model


class ProtocolMethod(str, Enum):
    INITIALIZE = "initialize"
    LIST_TOOLS = "tools/list"


class ProtocolOutcome(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


class CompletedProtocolRequest(Model):
    model_config = ConfigDict(frozen=True)

    method: ProtocolMethod
    outcome: ProtocolOutcome
    duration_seconds: float = Field(ge=0, allow_inf_nan=False)


class SuccessfulToolsList(Model):
    model_config = ConfigDict(frozen=True)

    tool_count: int = Field(ge=0)
