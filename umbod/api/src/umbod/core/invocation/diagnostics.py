from typing import Literal

from pydantic import BaseModel, ConfigDict


class InvocationFailureDiagnostic(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_mode: Literal["shared", "personal"]
    stage: Literal["downstream", "context", "admission", "authorization", "arguments", "output", "transport", "runtime"]
    reason: Literal[
        "downstream_exception", "downstream_tool_error", "context_unavailable",
        "admission_denied", "authorization_rejected", "authorization_health_unavailable",
        "invalid_arguments", "invalid_output", "contract_mismatch", "target_expired",
        "timeout", "transport_failure", "runtime_failure",
    ]


PERSONAL_RUNTIME_FAILURE = InvocationFailureDiagnostic(
    execution_mode="personal", stage="runtime", reason="runtime_failure",
)
