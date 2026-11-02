from typing import Any

import pytest
from fastmcp import FastMCP
from fastmcp.server.middleware import MiddlewareContext
from fastmcp.tools import FunctionTool, ToolResult
from mcp.types import CallToolRequestParams, CallToolResult

from umbod.build_identity import UMBOD_RELEASE, UMBOD_REVISION
from umbod.http_metadata import request_id_context
from umbod.mcp.middleware.response_metadata import McpResponseMetadataMiddleware
from umbod.mcp.responses.adapter import RESPONSE_METADATA_KEY, BuiltinToolResult
from umbod.mcp.signals import (
    McpInvocationPublisher,
    McpToolInvocationCompleted,
    McpToolInvocationFailed,
    McpToolInvocationSucceeded,
)
from umbod.mcp.tools.registration import McpObservedToolRegistrar, tool_result_is_error


@pytest.mark.asyncio
@pytest.mark.parametrize("registration_method", ["register", "register_tool"])
async def test_builtin_opt_in_preserves_schemas_and_success_payload(
    publisher: McpInvocationPublisher,
    completion_events: list[McpToolInvocationCompleted],
    registration_method: str,
) -> None:
    async def invoke(value: int) -> dict[str, int]:
        return {"value": value}

    delegate = FunctionTool.from_function(
        invoke, name="builtin", description="Inspect value."
    )
    registrar = McpObservedToolRegistrar(FastMCP("responses"), publisher)
    tool = (
        registrar.register(
            invoke,
            name="builtin",
            description="Inspect value.",
            auth=None,
            builtin_response=True,
        )
        if registration_method == "register"
        else registrar.register_tool(
            delegate,
            result_is_error=tool_result_is_error,
            operation_names=frozenset(),
            builtin_response=True,
        )
    )

    assert tool.parameters == delegate.parameters
    assert tool.output_schema == delegate.output_schema

    result = await tool.run({"value": 4})

    assert isinstance(result, BuiltinToolResult)
    assert result.structured_content == {"value": 4}
    assert result.meta[RESPONSE_METADATA_KEY]["guidance"]["outcome"] == "success"
    assert tool.parameters == delegate.parameters
    assert tool.output_schema == delegate.output_schema
    assert len(completion_events) == 1
    assert isinstance(completion_events[0], McpToolInvocationSucceeded)


@pytest.mark.asyncio
@pytest.mark.parametrize("registration_method", ["register", "register_tool"])
async def test_default_connector_result_is_unchanged_and_forged_metadata_gets_only_legacy_identity(
    publisher: McpInvocationPublisher,
    registration_method: str,
) -> None:
    forged = {
        "schema_version": 1,
        "request_id": "forged",
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
    returned = ToolResult(
        content="connector",
        structured_content={"value": 1},
        meta={
            "vendor": {"receipt": "kept"},
            RESPONSE_METADATA_KEY: forged,
        },
    )

    async def invoke() -> ToolResult:
        return returned

    registrar = McpObservedToolRegistrar(FastMCP("responses"), publisher)
    tool = (
        registrar.register(
            invoke, name="connector", description="Connector.", auth=None
        )
        if registration_method == "register"
        else registrar.register_tool(
            FunctionTool.from_function(invoke, name="connector"),
            result_is_error=tool_result_is_error,
            operation_names=frozenset(),
        )
    )
    direct = await tool.run({})
    assert direct is returned
    assert not isinstance(direct, BuiltinToolResult)

    async def call_next(
        context: MiddlewareContext[CallToolRequestParams],
    ) -> ToolResult:
        return await tool.run({})

    context = MiddlewareContext(
        message=CallToolRequestParams(name="connector"), method="tools/call"
    )
    with request_id_context("trusted-request"):
        result = await McpResponseMetadataMiddleware().on_call_tool(context, call_next)

    assert result.meta[RESPONSE_METADATA_KEY] == {
        "request_id": "trusted-request",
        "server_version": UMBOD_RELEASE,
        "server_revision": UMBOD_REVISION,
    }
    assert result.meta["vendor"] == {"receipt": "kept"}
    assert result.content == returned.content
    assert result.structured_content == returned.structured_content
    assert returned.meta[RESPONSE_METADATA_KEY] == forged


@pytest.mark.asyncio
async def test_registered_builtin_invalid_arguments_never_enter_body_and_emit_one_failure(
    publisher: McpInvocationPublisher,
    completion_events: list[McpToolInvocationCompleted],
) -> None:
    calls: list[int] = []

    async def invoke(value: int) -> dict[str, int]:
        calls.append(value)
        return {"value": value}

    tool = McpObservedToolRegistrar(FastMCP("responses"), publisher).register(
        invoke,
        name="builtin",
        description="Builtin.",
        auth=None,
        builtin_response=True,
    )
    result = await tool.run({"value": "secret-input"})
    metadata = result.meta[RESPONSE_METADATA_KEY]

    assert calls == []
    assert metadata["guidance"]["operation_state"] == "not_started"
    assert metadata["guidance"]["recovery"]["retry"] == "after_correction"
    assert metadata["guidance"]["error"]["code"] == "invalid_arguments"
    assert metadata["guidance"]["error"]["issues"][0]["field"] == "value"
    assert "secret-input" not in repr(result)
    assert len(completion_events) == 1
    assert isinstance(completion_events[0], McpToolInvocationFailed)


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_output", [{"value": "secret-output"}, None])
async def test_output_contract_failure_after_mutation_is_completed_without_replay_or_success(
    publisher: McpInvocationPublisher,
    completion_events: list[McpToolInvocationCompleted],
    invalid_output: Any,
) -> None:
    mutations: list[str] = []

    async def mutate() -> ToolResult:
        mutations.append("mutation")
        return ToolResult(content="secret-output", structured_content=invalid_output)

    tool = McpObservedToolRegistrar(FastMCP("responses"), publisher).register(
        mutate,
        name="mutate",
        description="Mutate.",
        auth=None,
        builtin_response=True,
    )
    tool.output_schema = {
        "type": "object",
        "properties": {"value": {"type": "integer"}},
        "required": ["value"],
    }
    result = await tool.run({})
    metadata = result.meta[RESPONSE_METADATA_KEY]

    assert mutations == ["mutation"]
    assert result.is_error
    assert result.structured_content is None
    assert metadata["guidance"]["operation_state"] == "completed"
    assert metadata["guidance"]["recovery"]["retry"] == "inspect_before_retry"
    assert metadata["guidance"]["error"]["code"] == "tool_response_contract_invalid"
    assert metadata["guidance"]["error"]["code"] in result.content[0].text
    assert metadata["guidance"]["error"]["message"] in result.content[0].text
    assert metadata["guidance"]["recovery"]["instructions"]
    for instruction in metadata["guidance"]["recovery"]["instructions"]:
        assert instruction in result.content[1].text
    assert "completed" in result.content[1].text
    assert "inspect_before_retry" in result.content[1].text
    assert "secret-output" not in repr(result)
    assert len(completion_events) == 1
    event = completion_events[0]
    assert isinstance(event, McpToolInvocationFailed)
    assert event.diagnostic.stage == "output"
    assert event.diagnostic.reason == "invalid_output"
    assert event.evidence.exception_type == "ToolResponseContractError"


@pytest.mark.asyncio
async def test_middleware_preserves_trusted_builtin_dto_and_adds_exactly_one_error_correlation(
    publisher: McpInvocationPublisher,
    completion_events: list[McpToolInvocationCompleted],
) -> None:
    calls: list[str] = []
    raw = CallToolResult.model_validate(
        {
            "content": [{"type": "text", "text": "Approved failure."}],
            "structuredContent": {"accepted": False},
            "isError": True,
            "_meta": {"vendor": {"receipt": "kept"}},
        }
    )

    async def invoke() -> ToolResult:
        calls.append("body")
        return ToolResult.from_mcp_result(raw)

    tool = McpObservedToolRegistrar(FastMCP("responses"), publisher).register(
        invoke,
        name="builtin",
        description="Builtin.",
        auth=None,
        builtin_response=True,
    )
    before: list[dict[str, Any]] = []

    async def call_next(
        context: MiddlewareContext[CallToolRequestParams],
    ) -> ToolResult:
        result = await tool.run({})
        before.append(result.meta[RESPONSE_METADATA_KEY])
        return result

    context = MiddlewareContext(
        message=CallToolRequestParams(name="builtin"), method="tools/call"
    )
    with request_id_context("correlation"):
        result = await McpResponseMetadataMiddleware().on_call_tool(context, call_next)

    assert calls == ["body"]
    assert result.meta[RESPONSE_METADATA_KEY] == before[0]
    assert result.meta[RESPONSE_METADATA_KEY]["request_id"] == "correlation"
    assert result.meta[RESPONSE_METADATA_KEY]["schema_version"] == 1
    assert result.meta[RESPONSE_METADATA_KEY]["guidance"]["outcome"] == "failure"
    assert result.meta["vendor"] == {"receipt": "kept"}
    assert result.structured_content == {"accepted": False}
    assert len(result.content) == 3
    assert result.content[0].text == "Approved failure."
    guidance = result.meta[RESPONSE_METADATA_KEY]["guidance"]
    assert guidance["error"]["code"] in result.content[1].text
    assert guidance["error"]["message"] in result.content[1].text
    assert result.content[2].text.count("Reference: correlation") == 1
    assert guidance["recovery"]["instructions"]
    for instruction in guidance["recovery"]["instructions"]:
        assert instruction in result.content[2].text
    assert len(completion_events) == 1
    assert isinstance(completion_events[0], McpToolInvocationFailed)
