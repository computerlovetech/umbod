from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from umbod.proxies import Model


_MachineCode = Annotated[
    str, StringConstraints(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
]
_ApprovedFieldPath = Annotated[
    str,
    StringConstraints(
        max_length=256,
        pattern=r"^(?:[A-Za-z_][A-Za-z0-9_]*(?:\.(?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+))*)?$",
    ),
]


class OperationState(StrEnum):
    NOT_STARTED = "not_started"
    COMPLETED = "completed"
    UNKNOWN = "unknown"


class RetryAdvice(StrEnum):
    NEVER = "never"
    AFTER_CORRECTION = "after_correction"
    AFTER_PERMISSION_CHANGE = "after_permission_change"
    AFTER_BACKOFF = "after_backoff"
    INSPECT_BEFORE_RETRY = "inspect_before_retry"


class ToolArgumentIssue(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    field: _ApprovedFieldPath
    reason: _MachineCode
    correction: Annotated[str, StringConstraints(min_length=1, max_length=256)]


class ToolErrorDetails(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: _MachineCode
    message: Annotated[str, StringConstraints(min_length=1, max_length=512)]
    issues: Annotated[tuple[ToolArgumentIssue, ...], Field(max_length=8)]


Instruction = Annotated[str, StringConstraints(min_length=1, max_length=512)]


class ToolNotice(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: _MachineCode
    message: Annotated[str, StringConstraints(min_length=1, max_length=512)]


class AgentGuidanceExtensions(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ClientMetadataExtensions(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ToolSuccessRecovery(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    retry: Literal["not_needed"]
    instructions: tuple[()]


class ToolFailureRecovery(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    retry: RetryAdvice
    instructions: Annotated[tuple[Instruction, ...], Field(min_length=1, max_length=8)]


class ToolSuccessGuidance(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: Literal["success"]
    operation_state: Literal["completed"]
    error: Literal[None]
    recovery: ToolSuccessRecovery
    notices: Annotated[tuple[ToolNotice, ...], Field(max_length=8)]
    extensions: AgentGuidanceExtensions


class ToolFailureGuidance(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: Literal["failure"]
    operation_state: OperationState
    error: ToolErrorDetails
    recovery: ToolFailureRecovery
    notices: Annotated[tuple[ToolNotice, ...], Field(max_length=8)]
    extensions: AgentGuidanceExtensions

    @model_validator(mode="after")
    def validate_retry_safety(self) -> Self:
        if (
            self.operation_state != OperationState.NOT_STARTED
            and self.recovery.retry
            not in (
                RetryAdvice.NEVER,
                RetryAdvice.INSPECT_BEFORE_RETRY,
            )
        ):
            raise ValueError(
                "Completed or unknown operations require conservative retry advice"
            )
        return self


ToolResponseGuidance = Annotated[
    ToolSuccessGuidance | ToolFailureGuidance, Field(discriminator="outcome")
]


class _CommonMetadata(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1]
    request_id: str
    server_version: str
    server_revision: str
    extensions: ClientMetadataExtensions


class ToolSuccessMetadata(_CommonMetadata):
    guidance: ToolSuccessGuidance


class ToolFailureMetadata(_CommonMetadata):
    guidance: ToolFailureGuidance


ToolResponseMetadata = ToolSuccessMetadata | ToolFailureMetadata
