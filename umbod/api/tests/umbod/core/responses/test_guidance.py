import pytest
from pydantic import BaseModel, ValidationError

from umbod.core.responses import (
    AgentGuidanceExtensions,
    ClientMetadataExtensions,
    OperationState,
    RetryAdvice,
    ToolErrorDetails,
    ToolFailureGuidance,
    ToolFailureMetadata,
    ToolFailureRecovery,
    ToolNotice,
    ToolResponseMetadataFactory,
    ToolSuccessGuidance,
    ToolSuccessMetadata,
    ToolSuccessRecovery,
)


@pytest.fixture
def response_models(
    metadata_factory: ToolResponseMetadataFactory, error_details: ToolErrorDetails
) -> tuple[BaseModel, ...]:
    success = metadata_factory.success("request", notices=())
    failure = metadata_factory.failure(
        "request",
        error=error_details,
        operation_state=OperationState.NOT_STARTED,
        retry=RetryAdvice.NEVER,
        instructions=(),
        notices=(),
    )
    return (
        success,
        failure,
        success.guidance,
        failure.guidance,
        success.guidance.recovery,
        failure.guidance.recovery,
        success.extensions,
        success.guidance.extensions,
        ToolNotice(code="limited", message="Results are limited."),
    )


def test_every_response_model_field_is_required(
    response_models: tuple[BaseModel, ...],
) -> None:
    for model in response_models:
        for field in type(model).model_fields:
            assert type(model).model_fields[field].is_required()
            data = model.model_dump()
            del data[field]
            with pytest.raises(ValidationError, match="Field required"):
                type(model).model_validate(data)


def test_every_response_model_forbids_extra_fields(
    response_models: tuple[BaseModel, ...],
) -> None:
    for model in response_models:
        with pytest.raises(ValidationError, match="Extra inputs"):
            type(model).model_validate({**model.model_dump(), "unknown": "value"})


def test_every_nested_response_model_is_frozen(
    response_models: tuple[BaseModel, ...],
) -> None:
    for model in response_models:
        assert type(model).model_config["frozen"] is True
        for field in type(model).model_fields:
            with pytest.raises(ValidationError, match="frozen"):
                setattr(model, field, getattr(model, field))


@pytest.mark.parametrize("model", [AgentGuidanceExtensions, ClientMetadataExtensions])
@pytest.mark.parametrize(
    "namespace", ["arbitrary", "computerlove.tech/umbod", "vendor.example/v1"]
)
def test_extensions_reject_every_unapproved_namespace(
    model: type[BaseModel], namespace: str
) -> None:
    assert model.model_fields == {}
    with pytest.raises(ValidationError, match="Extra inputs"):
        model.model_validate({namespace: {"value": "unapproved"}})


def test_extension_surfaces_are_distinct_types() -> None:
    with pytest.raises(ValidationError):
        ToolSuccessGuidance.model_validate(
            {
                "outcome": "success",
                "operation_state": "completed",
                "error": None,
                "recovery": {"retry": "not_needed", "instructions": ()},
                "notices": (),
                "extensions": ClientMetadataExtensions(),
            }
        )


@pytest.mark.parametrize("instructions", [(), ("",), ("a" * 513,), ("safe",) * 9])
def test_failure_recovery_rejects_invalid_instructions(
    instructions: tuple[str, ...],
) -> None:
    with pytest.raises(ValidationError):
        ToolFailureRecovery(retry=RetryAdvice.NEVER, instructions=instructions)


def test_failure_recovery_accepts_instruction_bounds() -> None:
    recovery = ToolFailureRecovery(
        retry=RetryAdvice.NEVER, instructions=("a" * 512,) * 8
    )
    assert len(recovery.instructions) == 8


@pytest.mark.parametrize("instructions", [("Do something.",), ("",)])
def test_success_recovery_forbids_nonempty_instructions(
    instructions: tuple[str, ...],
) -> None:
    with pytest.raises(ValidationError):
        ToolSuccessRecovery.model_validate(
            {"retry": "not_needed", "instructions": instructions}
        )


@pytest.mark.parametrize("retry", list(RetryAdvice))
def test_success_recovery_rejects_failure_retry_advice(retry: RetryAdvice) -> None:
    with pytest.raises(ValidationError):
        ToolSuccessRecovery.model_validate({"retry": retry, "instructions": ()})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("code", ""),
        ("code", "a" * 65),
        ("code", "Invalid"),
        ("code", "invalid code"),
        ("message", ""),
        ("message", "a" * 513),
    ],
)
def test_notice_rejects_invalid_fields(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        ToolNotice.model_validate(
            {"code": "notice", "message": "Approved notice.", field: value}
        )


def test_notice_accepts_upper_bounds() -> None:
    notice = ToolNotice(code="a" * 64, message="a" * 512)
    assert len(notice.message) == 512


@pytest.mark.parametrize("model", [ToolSuccessGuidance, ToolFailureGuidance])
def test_guidance_enforces_notice_limit_and_copies_collections(
    response_models: tuple[BaseModel, ...], model: type[BaseModel]
) -> None:
    original = next(value for value in response_models if type(value) is model)
    notice = ToolNotice(code="limited", message="Results are limited.")
    notices = [notice] * 8
    guidance = model.model_validate({**original.model_dump(), "notices": notices})
    notices.clear()
    assert guidance.notices == (notice,) * 8
    with pytest.raises(ValidationError, match="at most 8"):
        model.model_validate({**original.model_dump(), "notices": [notice] * 9})


@pytest.mark.parametrize(
    "operation_state", [OperationState.UNKNOWN, OperationState.COMPLETED]
)
@pytest.mark.parametrize(
    "retry",
    [
        RetryAdvice.AFTER_CORRECTION,
        RetryAdvice.AFTER_PERMISSION_CHANGE,
        RetryAdvice.AFTER_BACKOFF,
    ],
)
def test_direct_guidance_construction_enforces_retry_safety(
    error_details: ToolErrorDetails, operation_state: OperationState, retry: RetryAdvice
) -> None:
    with pytest.raises(ValidationError, match="conservative retry advice"):
        ToolFailureGuidance(
            outcome="failure",
            operation_state=operation_state,
            error=error_details,
            recovery=ToolFailureRecovery(
                retry=retry, instructions=("Approved instruction.",)
            ),
            notices=(),
            extensions=AgentGuidanceExtensions(),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operation_state", "unknown"),
        ("error", {"code": "error", "message": "Failed.", "issues": []}),
        ("outcome", "failure"),
    ],
)
def test_success_guidance_rejects_inconsistent_values(
    metadata_factory: ToolResponseMetadataFactory, field: str, value: object
) -> None:
    data = metadata_factory.success("request", notices=()).guidance.model_dump()
    with pytest.raises(ValidationError):
        ToolSuccessGuidance.model_validate({**data, field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operation_state", "pending"),
        ("error", None),
        ("outcome", "success"),
        ("recovery", {"retry": "not_needed", "instructions": ("Approved.",)}),
    ],
)
def test_failure_guidance_rejects_inconsistent_values(
    response_models: tuple[BaseModel, ...], field: str, value: object
) -> None:
    guidance = next(
        model for model in response_models if isinstance(model, ToolFailureGuidance)
    )
    with pytest.raises(ValidationError):
        ToolFailureGuidance.model_validate({**guidance.model_dump(), field: value})


@pytest.mark.parametrize("model", [ToolSuccessMetadata, ToolFailureMetadata])
@pytest.mark.parametrize("unsupported_version", [0, 2])
def test_metadata_rejects_unsupported_versions_flat_fields_and_opposite_guidance(
    response_models: tuple[BaseModel, ...], model: type[BaseModel], unsupported_version: int
) -> None:
    metadata = next(value for value in response_models if type(value) is model)
    opposite = next(
        value
        for value in response_models
        if isinstance(value, (ToolSuccessMetadata, ToolFailureMetadata))
        and type(value) is not model
    )
    for field in ("outcome", "operation_state", "error", "retry"):
        assert not hasattr(metadata, field)
        with pytest.raises(ValidationError, match="Extra inputs"):
            model.model_validate({**metadata.model_dump(), field: "unexpected"})
    with pytest.raises(ValidationError):
        model.model_validate({**metadata.model_dump(), "schema_version": unsupported_version})
    with pytest.raises(ValidationError):
        model.model_validate(
            {**metadata.model_dump(), "guidance": opposite.guidance.model_dump()}
        )


def test_instruction_input_list_is_copied() -> None:
    instructions = ["Approved instruction."]
    recovery = ToolFailureRecovery.model_validate(
        {"retry": "never", "instructions": instructions}
    )
    instructions.clear()
    assert recovery.instructions == ("Approved instruction.",)
