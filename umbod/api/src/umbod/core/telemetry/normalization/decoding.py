from typing import Annotated, Literal

from pydantic import Field

from .models import CorrelationKey, NormalizationModel, ProducerFieldKey


class DecodedString(NormalizationModel):
    kind: Literal["string"]
    value: str


class DecodedBoolean(NormalizationModel):
    kind: Literal["boolean"]
    value: bool


class DecodedNumber(NormalizationModel):
    kind: Literal["number"]
    value: float


class DecodedInteger(NormalizationModel):
    kind: Literal["integer"]
    value: Annotated[int, Field(strict=True)]


class DecodedInvalid(NormalizationModel):
    kind: Literal["invalid"]
    reason: Literal["wrong_type", "oversize"]


DecodedValue = Annotated[DecodedString | DecodedBoolean | DecodedNumber | DecodedInteger | DecodedInvalid, Field(discriminator="kind")]
LegacyProducerKey = Literal[
    "umbod.activity.kind", "umbod.activity.outcome", "success", "tool.name", "tool_name", "mcp.tool.name",
    "tool_type", "tool.type", "tool_kind", "tool.kind", "tool_origin", "tool_namespace",
    "mcp_server", "mcp_server_origin", "mcp.server.name", "duration_ms", "duration_ms_total",
    "duration", "duration_seconds", "duration_ns", "decision", "invocation_trigger", "app.version", "skill.invocation_type",
]

ProducerKey = Literal[LegacyProducerKey, ProducerFieldKey]


class DecodedAttribute(NormalizationModel):
    key: ProducerKey | CorrelationKey
    value: DecodedValue
