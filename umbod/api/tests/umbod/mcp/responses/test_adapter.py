import asyncio
import json
from typing import Any

import pytest
from fastmcp.exceptions import AuthorizationError, ValidationError
from fastmcp.tools import InputRequiredToolResult, ToolResult
from mcp.types import CallToolResult, InputRequiredResult
from pydantic import ValidationError as ModelValidationError
from pydantic_core import PydanticCustomError

from umbod.core.responses import RetryAdvice, ToolErrorDetails
from umbod.http_metadata import current_request_id, request_id_context
from umbod.mcp.responses.adapter import (
    RESPONSE_METADATA_KEY,
    BuiltinToolResponseAdapter,
    BuiltinToolResult,
)
from umbod.mcp.responses.progress import operation_completed, operation_started
from umbod.mcp.tools.errors import (
    BuiltinToolArgumentError,
    BuiltinToolAuthorizationDenied,
    BuiltinToolError,
)


@pytest.mark.asyncio
async def test_success_preserves_raw_wire_fields_without_mutating_source(
    adapter: BuiltinToolResponseAdapter,
) -> None:
    raw = CallToolResult.model_validate(
        {
            "content": [
                {"type": "text", "text": "unchanged", "annotations": {"priority": 0.5}}
            ],
            "structuredContent": {"value": 4},
            "isError": False,
            "_meta": {
                "vendor": {"receipt": "original"},
                RESPONSE_METADATA_KEY: {"forged": True},
            },
            "vendorExtension": {"opaque": [1, 2]},
        }
    )
    original = raw.model_dump(mode="json", by_alias=True)

    async def invoke(arguments: dict[str, Any]) -> ToolResult:
        return ToolResult.from_mcp_result(raw)

    with request_id_context("request"):
        result = await adapter.invoke(invoke, {"value": 4})
    wire = result.to_mcp_result()

    assert isinstance(result, BuiltinToolResult)
    assert isinstance(wire, CallToolResult)
    actual = wire.model_dump(mode="json", by_alias=True)
    expected = {
        **original,
        "content": actual["content"],
        "_meta": {
            "vendor": {"receipt": "original"},
            RESPONSE_METADATA_KEY: {
                "schema_version": 1,
                "request_id": "request",
                "server_version": "release",
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
            },
        },
    }
    assert actual == expected
    assert len(wire.content) == 3
    assert actual["content"][0] == original["content"][0]
    assert json.loads(wire.content[1].text) == {"value": 4}
    assert "success" in wire.content[2].text
    assert "completed" in wire.content[2].text
    assert raw.model_dump(mode="json", by_alias=True) == original


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_type", "retry"),
    [
        (BuiltinToolArgumentError, "after_correction"),
        (BuiltinToolAuthorizationDenied, "after_permission_change"),
        (BuiltinToolError, "never"),
    ],
)
async def test_typed_rejections_before_admission_are_not_started(
    adapter: BuiltinToolResponseAdapter,
    error_type: type[Exception],
    retry: str,
) -> None:
    details = ToolErrorDetails(
        code="rejected", message="Approved rejection.", issues=()
    )
    if error_type is BuiltinToolError:
        error = BuiltinToolError("Approved rejection.", details=details, retry=RetryAdvice.NEVER)
    elif error_type is BuiltinToolArgumentError:
        error = BuiltinToolArgumentError("Approved rejection.", details=details, notices=())
    else:
        error = error_type("Approved rejection.", details=details)

    async def invoke(arguments: dict[str, Any]) -> ToolResult:
        raise error

    result = await adapter.invoke(invoke, {})
    metadata = result.meta[RESPONSE_METADATA_KEY]

    assert result.is_error
    assert metadata["guidance"]["operation_state"] == "not_started"
    assert metadata["guidance"]["recovery"]["retry"] == retry
    assert metadata["guidance"]["error"] == details.model_dump(mode="json")
    stripped = result.to_mcp_result().model_copy(update={"meta": None})
    assert stripped.meta is None
    assert len(stripped.content) == 2
    assert details.code in stripped.content[0].text
    assert details.message in stripped.content[0].text
    guidance = metadata["guidance"]
    assert guidance["recovery"]["instructions"]
    for value in (guidance["outcome"], guidance["operation_state"], retry, metadata["request_id"]):
        assert value in stripped.content[1].text
    for instruction in guidance["recovery"]["instructions"]:
        assert instruction in stripped.content[1].text
    for notice in guidance["notices"]:
        assert notice["code"] in stripped.content[1].text
        assert notice["message"] in stripped.content[1].text


@pytest.mark.asyncio
@pytest.mark.parametrize("completed", [False, True])
async def test_typed_argument_rejection_after_admission_retains_conservative_state_and_retry(
    adapter: BuiltinToolResponseAdapter,
    completed: bool,
) -> None:
    details = ToolErrorDetails(
        code="rejected", message="Approved rejection.", issues=()
    )

    async def invoke(arguments: dict[str, Any]) -> ToolResult:
        operation_started()
        if completed:
            operation_completed()
        raise BuiltinToolArgumentError("Approved rejection.", details=details, notices=())

    result = await adapter.invoke(invoke, {})

    assert result.meta[RESPONSE_METADATA_KEY]["guidance"]["operation_state"] == (
        "completed" if completed else "unknown"
    )
    assert result.meta[RESPONSE_METADATA_KEY]["guidance"]["recovery"]["retry"] == "inspect_before_retry"
    assert result.meta[RESPONSE_METADATA_KEY]["guidance"]["error"] == details.model_dump(
        mode="json"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("wrapped", [False, True])
async def test_argument_validation_before_admission_exposes_only_approved_paths_and_codes(
    adapter: BuiltinToolResponseAdapter,
    wrapped: bool,
) -> None:
    failure = ModelValidationError.from_exception_data(
        "SecretModelType",
        [
            {"type": "int_parsing", "loc": ("value",), "input": "secret-input"},
            {
                "type": "extra_forbidden",
                "loc": ("secret-unknown-key",),
                "input": "secret-input",
            },
            {
                "type": PydanticCustomError(
                    "SecretRuntimeType", "{private}", {"private": "secret-context"}
                ),
                "loc": ("value",),
                "input": "secret-input",
            },
        ],
    )

    async def invoke(arguments: dict[str, Any]) -> ToolResult:
        if wrapped:
            raise ValidationError("secret-wrapper-message") from failure
        raise failure

    result = await adapter.invoke(invoke, {})
    metadata = result.meta[RESPONSE_METADATA_KEY]
    serialized = json.dumps(result.to_mcp_result().model_dump(mode="json"))

    assert metadata["guidance"]["operation_state"] == "not_started"
    assert metadata["guidance"]["recovery"]["retry"] == "after_correction"
    assert metadata["guidance"]["error"]["code"] == "invalid_arguments"
    assert metadata["guidance"]["error"]["issues"] == [
        {
            "field": "value",
            "reason": "invalid_type",
            "correction": "Use the schema-declared type: integer.",
        },
        {
            "field": "arguments",
            "reason": "undeclared_field",
            "correction": "Remove undeclared fields.",
        },
        {
            "field": "value",
            "reason": "invalid_value",
            "correction": "Use the schema-declared type: integer.",
        },
    ]
    guidance = metadata["guidance"]
    assert guidance["recovery"]["instructions"]
    for issue in guidance["error"]["issues"]:
        assert issue["field"] in result.content[0].text
        assert issue["correction"] in result.content[0].text
    for instruction in guidance["recovery"]["instructions"]:
        assert instruction in result.content[1].text
    assert "secret" not in serialized.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("completed", [False, True])
@pytest.mark.parametrize("wrapped", [False, True])
async def test_validation_after_admission_is_not_an_argument_rejection(
    adapter: BuiltinToolResponseAdapter,
    completed: bool,
    wrapped: bool,
) -> None:
    failure = ModelValidationError.from_exception_data(
        "SecretType",
        [{"type": "int_parsing", "loc": ("value",), "input": "secret-input"}],
    )

    async def invoke(arguments: dict[str, Any]) -> ToolResult:
        operation_started()
        if completed:
            operation_completed()
        if wrapped:
            raise ValidationError("secret-wrapper") from failure
        raise failure

    result = await adapter.invoke(invoke, {})
    metadata = result.meta[RESPONSE_METADATA_KEY]

    assert metadata["guidance"]["operation_state"] == ("completed" if completed else "unknown")
    assert metadata["guidance"]["recovery"]["retry"] == "inspect_before_retry"
    assert metadata["guidance"]["error"]["code"] == "tool_operation_failed"
    assert metadata["guidance"]["error"]["issues"] == []
    assert "secret" not in repr(result).lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("started", [False, True])
async def test_unknown_exception_is_sanitized_and_conservative(
    adapter: BuiltinToolResponseAdapter,
    started: bool,
) -> None:
    async def invoke(arguments: dict[str, Any]) -> ToolResult:
        if started:
            operation_started()
        raise RuntimeError("secret-credential private-payload")

    result = await adapter.invoke(invoke, {})

    assert result.is_error
    assert result.meta[RESPONSE_METADATA_KEY]["guidance"]["operation_state"] == "unknown"
    assert result.meta[RESPONSE_METADATA_KEY]["guidance"]["recovery"]["retry"] == "inspect_before_retry"
    assert (
        result.meta[RESPONSE_METADATA_KEY]["guidance"]["error"]["code"] == "tool_operation_failed"
    )
    assert "secret-credential" not in repr(result)
    assert "private-payload" not in repr(result)


@pytest.mark.asyncio
async def test_body_returned_error_preserves_payload_but_never_invites_blind_retry(
    adapter: BuiltinToolResponseAdapter,
) -> None:
    returned = ToolResult(
        content="Approved failure.",
        structured_content={"accepted": False},
        is_error=True,
    )

    async def invoke(arguments: dict[str, Any]) -> ToolResult:
        return returned

    result = await adapter.invoke(invoke, {})

    assert result.content[:len(returned.content)] == returned.content
    error = result.meta[RESPONSE_METADATA_KEY]["guidance"]["error"]
    assert error["code"] in result.content[-2].text
    assert error["message"] in result.content[-2].text
    assert result.structured_content == returned.structured_content
    assert result.meta[RESPONSE_METADATA_KEY]["guidance"]["operation_state"] == "unknown"
    assert result.meta[RESPONSE_METADATA_KEY]["guidance"]["recovery"]["retry"] == "inspect_before_retry"
    assert (
        result.meta[RESPONSE_METADATA_KEY]["guidance"]["error"]["code"] == "tool_returned_failure"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [AuthorizationError("denied"), asyncio.CancelledError()]
)
async def test_authorization_and_cancellation_pass_through_by_identity(
    adapter: BuiltinToolResponseAdapter,
    error: BaseException,
) -> None:
    calls: list[str] = []

    async def invoke(arguments: dict[str, Any]) -> ToolResult:
        calls.append("called")
        raise error

    with pytest.raises(type(error)) as caught:
        await adapter.invoke(invoke, {})

    assert caught.value is error
    assert calls == ["called"]
    assert current_request_id() is None


@pytest.mark.asyncio
async def test_input_required_result_passes_through_by_identity(
    adapter: BuiltinToolResponseAdapter,
) -> None:
    returned = InputRequiredToolResult(InputRequiredResult(request_state="pending"))

    async def invoke(arguments: dict[str, Any]) -> ToolResult:
        return returned

    assert await adapter.invoke(invoke, {}) is returned
