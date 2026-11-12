from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class NoDownstreamResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["no_response"] = "no_response"


class DownstreamHttpResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["http_response"] = "http_response"
    status_code: int = Field(ge=100, le=599)


DownstreamResponseEvidence = Annotated[NoDownstreamResponse | DownstreamHttpResponse, Field(discriminator="kind")]


class NoInvocationFailureDiagnostic(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class InvocationFailureDiagnostic(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_mode: Literal["shared", "personal"]
    stage: Literal["downstream", "context", "admission", "authorization", "arguments", "output", "transport", "runtime"]
    reason: Literal[
        "downstream_exception", "downstream_tool_error", "context_unavailable",
        "admission_denied", "authorization_rejected", "authorization_health_unavailable",
        "invalid_arguments", "invalid_output", "contract_mismatch", "target_expired",
        "timeout", "transport_failure", "runtime_failure", "http_rejected",
        "content_encoding_rejected", "charset_rejected", "invalid_content_length",
        "response_size_exceeded", "aggregate_size_exceeded", "request_size_exceeded",
        "protocol_rejected", "network_failure",
    ]
    downstream_response: DownstreamResponseEvidence = NoDownstreamResponse()


PERSONAL_RUNTIME_FAILURE = InvocationFailureDiagnostic(
    execution_mode="personal", stage="runtime", reason="runtime_failure",
)
