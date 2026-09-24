from enum import StrEnum

from pydantic import BaseModel, ConfigDict, PositiveFloat


class InvocationOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class CompletedToolInvocation(BaseModel):
    model_config = ConfigDict(frozen=True)

    connector_name: str
    tool_name: str
    outcome: InvocationOutcome
    duration_seconds: PositiveFloat
