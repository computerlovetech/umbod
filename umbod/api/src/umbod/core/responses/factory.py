from dataclasses import dataclass

from .models import (
    AgentGuidanceExtensions,
    ClientMetadataExtensions,
    OperationState,
    RetryAdvice,
    ToolErrorDetails,
    ToolFailureGuidance,
    ToolFailureMetadata,
    ToolFailureRecovery,
    ToolNotice,
    ToolSuccessGuidance,
    ToolSuccessMetadata,
    ToolSuccessRecovery,
)


_STANDARD_INSTRUCTIONS: dict[RetryAdvice, str] = {
    RetryAdvice.NEVER: "Do not retry this operation.",
    RetryAdvice.AFTER_CORRECTION: "Correct the reported arguments or conditions before retrying.",
    RetryAdvice.AFTER_PERMISSION_CHANGE: "Obtain the required permission before retrying.",
    RetryAdvice.AFTER_BACKOFF: "Wait before retrying the operation.",
    RetryAdvice.INSPECT_BEFORE_RETRY: "Do not retry automatically; inspect the operation state before retrying.",
}
_INSPECTION_INSTRUCTIONS: dict[OperationState, str] = {
    OperationState.UNKNOWN: "Do not retry automatically; inspect the operation state because the operation may have completed.",
    OperationState.COMPLETED: "Do not retry automatically; inspect the operation state because the operation already completed.",
    OperationState.NOT_STARTED: _STANDARD_INSTRUCTIONS[
        RetryAdvice.INSPECT_BEFORE_RETRY
    ],
}


@dataclass(frozen=True)
class ToolResponseMetadataFactory:
    server_version: str
    server_revision: str

    def success(
        self, request_id: str, *, notices: tuple[ToolNotice, ...]
    ) -> ToolSuccessMetadata:
        return ToolSuccessMetadata(
            schema_version=1,
            request_id=request_id,
            server_version=self.server_version,
            server_revision=self.server_revision,
            guidance=ToolSuccessGuidance(
                outcome="success",
                operation_state="completed",
                error=None,
                recovery=ToolSuccessRecovery(retry="not_needed", instructions=()),
                notices=notices,
                extensions=AgentGuidanceExtensions(),
            ),
            extensions=ClientMetadataExtensions(),
        )

    def failure(
        self,
        request_id: str,
        *,
        error: ToolErrorDetails,
        operation_state: OperationState,
        retry: RetryAdvice,
        instructions: tuple[str, ...],
        notices: tuple[ToolNotice, ...],
    ) -> ToolFailureMetadata:
        standard_instruction = (
            _INSPECTION_INSTRUCTIONS[operation_state]
            if retry == RetryAdvice.INSPECT_BEFORE_RETRY
            else _STANDARD_INSTRUCTIONS[retry]
        )
        return ToolFailureMetadata(
            schema_version=1,
            request_id=request_id,
            server_version=self.server_version,
            server_revision=self.server_revision,
            guidance=ToolFailureGuidance(
                outcome="failure",
                operation_state=operation_state,
                recovery=ToolFailureRecovery(
                    retry=retry, instructions=(standard_instruction, *instructions)
                ),
                error=error,
                notices=notices,
                extensions=AgentGuidanceExtensions(),
            ),
            extensions=ClientMetadataExtensions(),
        )
