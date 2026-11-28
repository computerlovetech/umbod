from typing import Annotated, Generic, Literal, TypeVar, Union

from pydantic import ConfigDict, Field

from umbod.proxies import Model

Count = Annotated[int, Field(ge=0)]
ValueT = TypeVar("ValueT")


class Available(Model, Generic[ValueT]):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["available"]
    value: ValueT


class Unavailable(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["unavailable"]


class ToolCounts(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: Count
    known: Count


class AttentionCounts(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    unconfigured: Count
    draft: Count
    unpublished: Count
    unhealthy: Count


class ConnectorCounts(AttentionCounts):
    configured: Count
    published: Count


class OverviewBreakdown(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["catalog", "openapi", "mcp"]
    connectors: Union[Available[ConnectorCounts], Unavailable]
    tools: Union[Available[ToolCounts], Unavailable]


class OverviewSnapshot(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    breakdown: tuple[OverviewBreakdown, OverviewBreakdown, OverviewBreakdown]
    permission_groups: Union[Available[Count], Unavailable]


class AdminOverview(OverviewSnapshot):
    configured: Union[Available[Count], Unavailable]
    published: Union[Available[Count], Unavailable]
    tools: Union[Available[ToolCounts], Unavailable]
    attention: Union[Available[AttentionCounts], Unavailable]
