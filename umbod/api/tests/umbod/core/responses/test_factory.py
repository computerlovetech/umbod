import json

import pytest
from pydantic import TypeAdapter, ValidationError

from umbod.core.responses import (
    OperationState,
    RetryAdvice,
    ToolErrorDetails,
    ToolNotice,
    ToolResponseGuidance,
    ToolResponseMetadata,
    ToolResponseMetadataFactory,
)


def test_success_preserves_identity_and_has_explicit_null_error(
    metadata_factory: ToolResponseMetadataFactory,
) -> None:
    metadata = metadata_factory.success("request-one", notices=())

    assert json.loads(metadata.model_dump_json()) == {
        "schema_version": 1,
        "request_id": "request-one",
        "server_version": "1.2.3",
        "server_revision": "revision",
        "guidance": {
            "outcome": "success",
            "operation_state": "completed",
            "error": None,
            "recovery": {"retry": "not_needed", "instructions": []},
            "notices": [],
            "extensions": {},
        },
        "extensions": {},
    }


def test_failure_preserves_error_and_identity(
    metadata_factory: ToolResponseMetadataFactory,
    error_details: ToolErrorDetails,
) -> None:
    metadata = metadata_factory.failure(
        "request-two",
        error=error_details,
        operation_state=OperationState.NOT_STARTED,
        retry=RetryAdvice.AFTER_CORRECTION,
        instructions=("Supply a name.",),
        notices=(),
    )

    assert json.loads(metadata.model_dump_json()) == {
        "schema_version": 1,
        "request_id": "request-two",
        "server_version": "1.2.3",
        "server_revision": "revision",
        "guidance": {
            "outcome": "failure",
            "operation_state": "not_started",
            "recovery": {
                "retry": "after_correction",
                "instructions": [
                    "Correct the reported arguments or conditions before retrying.",
                    "Supply a name.",
                ],
            },
            "error": error_details.model_dump(mode="json"),
            "notices": [],
            "extensions": {},
        },
        "extensions": {},
    }


@pytest.mark.parametrize("operation_state", list(OperationState))
@pytest.mark.parametrize("retry", list(RetryAdvice))
def test_failure_allows_only_safe_state_retry_combinations(
    metadata_factory: ToolResponseMetadataFactory,
    error_details: ToolErrorDetails,
    operation_state: OperationState,
    retry: RetryAdvice,
) -> None:
    if operation_state != OperationState.NOT_STARTED and retry not in (
        RetryAdvice.NEVER,
        RetryAdvice.INSPECT_BEFORE_RETRY,
    ):
        with pytest.raises(ValidationError, match="conservative retry advice"):
            metadata_factory.failure(
                "request",
                error=error_details,
                operation_state=operation_state,
                retry=retry,
                instructions=(),
                notices=(),
            )
    else:
        metadata = metadata_factory.failure(
            "request",
            error=error_details,
            operation_state=operation_state,
            retry=retry,
            instructions=(),
            notices=(),
        )
        assert (
            metadata.guidance.operation_state,
            metadata.guidance.recovery.retry,
        ) == (
            operation_state,
            retry,
        )


@pytest.mark.parametrize(
    ("operation_state", "retry", "expected"),
    [
        (OperationState.NOT_STARTED, RetryAdvice.NEVER, "Do not retry"),
        (
            OperationState.NOT_STARTED,
            RetryAdvice.AFTER_CORRECTION,
            "Correct the reported arguments or conditions",
        ),
        (
            OperationState.NOT_STARTED,
            RetryAdvice.AFTER_PERMISSION_CHANGE,
            "Obtain the required permission",
        ),
        (OperationState.NOT_STARTED, RetryAdvice.AFTER_BACKOFF, "Wait"),
        (
            OperationState.NOT_STARTED,
            RetryAdvice.INSPECT_BEFORE_RETRY,
            "Do not retry automatically; inspect",
        ),
        (
            OperationState.UNKNOWN,
            RetryAdvice.INSPECT_BEFORE_RETRY,
            "Do not retry automatically; inspect the operation state because the operation may have completed.",
        ),
        (
            OperationState.COMPLETED,
            RetryAdvice.INSPECT_BEFORE_RETRY,
            "Do not retry automatically; inspect the operation state because the operation already completed.",
        ),
    ],
)
def test_standard_recovery_instruction_precedes_domain_instructions(
    metadata_factory: ToolResponseMetadataFactory,
    error_details: ToolErrorDetails,
    operation_state: OperationState,
    retry: RetryAdvice,
    expected: str,
) -> None:
    metadata = metadata_factory.failure(
        "request",
        error=error_details,
        operation_state=operation_state,
        retry=retry,
        instructions=("Review the approved target.",),
        notices=(),
    )

    assert metadata.guidance.recovery.instructions[0].startswith(expected)
    assert metadata.guidance.recovery.instructions[1:] == (
        "Review the approved target.",
    )


@pytest.mark.parametrize("outcome", ["success", "failure"])
def test_union_roundtrips_json_with_narrowed_guidance(
    metadata_factory: ToolResponseMetadataFactory,
    error_details: ToolErrorDetails,
    outcome: str,
) -> None:
    metadata = (
        metadata_factory.success("request", notices=())
        if outcome == "success"
        else metadata_factory.failure(
            "request",
            error=error_details,
            operation_state=OperationState.UNKNOWN,
            retry=RetryAdvice.INSPECT_BEFORE_RETRY,
            instructions=(),
            notices=(),
        )
    )
    restored = TypeAdapter(ToolResponseMetadata).validate_json(
        metadata.model_dump_json()
    )
    restored_guidance = TypeAdapter(ToolResponseGuidance).validate_json(
        metadata.guidance.model_dump_json()
    )

    assert type(restored) is type(metadata)
    assert restored == metadata
    assert type(restored_guidance) is type(metadata.guidance)
    assert restored_guidance == metadata.guidance


@pytest.mark.parametrize("outcome", ["success", "failure"])
def test_factory_preserves_notices(
    metadata_factory: ToolResponseMetadataFactory,
    error_details: ToolErrorDetails,
    outcome: str,
) -> None:
    notices = (ToolNotice(code="limited", message="Results are limited."),)
    metadata = (
        metadata_factory.success("request", notices=notices)
        if outcome == "success"
        else metadata_factory.failure(
            "request",
            error=error_details,
            operation_state=OperationState.NOT_STARTED,
            retry=RetryAdvice.NEVER,
            notices=notices,
            instructions=(),
        )
    )

    assert metadata.guidance.notices == notices


def test_factory_instruction_limit_includes_standard_instruction(
    metadata_factory: ToolResponseMetadataFactory, error_details: ToolErrorDetails
) -> None:
    metadata = metadata_factory.failure(
        "request",
        error=error_details,
        operation_state=OperationState.NOT_STARTED,
        retry=RetryAdvice.NEVER,
        instructions=("Approved instruction.",) * 7,
        notices=(),
    )
    assert len(metadata.guidance.recovery.instructions) == 8

    with pytest.raises(ValidationError, match="at most 8"):
        metadata_factory.failure(
            "request",
            error=error_details,
            operation_state=OperationState.NOT_STARTED,
            retry=RetryAdvice.NEVER,
            instructions=("Approved instruction.",) * 8,
            notices=(),
        )


@pytest.mark.parametrize("outcome", ["unexpected", "", None])
def test_discriminated_guidance_rejects_unknown_outcomes(outcome: object) -> None:
    with pytest.raises(ValidationError, match="union_tag"):
        TypeAdapter(ToolResponseGuidance).validate_python({"outcome": outcome})
