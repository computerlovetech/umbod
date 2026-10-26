from enum import StrEnum

from pydantic import BaseModel, ConfigDict, PositiveFloat


class InvocationOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class InvocationScope(StrEnum):
    CONNECTOR = "connector"
    REQUEST = "request"


class ToolInvocationMetricIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)

    scope: InvocationScope
    connector_name: str
    tool_name: str


class CompletedToolInvocation(BaseModel):
    model_config = ConfigDict(frozen=True)

    scope: InvocationScope
    connector_name: str
    tool_name: str
    outcome: InvocationOutcome
    duration_seconds: PositiveFloat
