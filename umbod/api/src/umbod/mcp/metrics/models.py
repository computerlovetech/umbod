from enum import StrEnum

from pydantic import ConfigDict, PositiveFloat

from umbod.proxies import Model


class InvocationOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class InvocationScope(StrEnum):
    CONNECTOR = "connector"
    REQUEST = "request"


class ToolInvocationMetricIdentity(Model):
    model_config = ConfigDict(frozen=True)

    scope: InvocationScope
    connector_name: str
    tool_name: str


class CompletedToolInvocation(Model):
    model_config = ConfigDict(frozen=True)

    scope: InvocationScope
    connector_name: str
    tool_name: str
    outcome: InvocationOutcome
    duration_seconds: PositiveFloat
