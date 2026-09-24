from typing import cast

import pytest
from pydantic import JsonValue, ValidationError

from umbod.mcp.connectors.tools.deployment_modes.codemode.sandbox import (
    FastMcpMontyCodeModeAdapter,
    OpenApiCodeModeInvocation,
)
from umbod.mcp.connectors.tools.infrastructure.authorization import (
    UnrestrictedConnectorTools,
)
from umbod.mcp.connectors.tools.runtime.registry import RuntimeConnectorToolRegistry


def test_openapi_invocation_is_strict_and_frozen() -> None:
    invocation = OpenApiCodeModeInvocation(
        connector_id="c",
        operation_id="operation",
        path={},
        query={},
        headers={},
        body={"state": "missing"},
    )

    with pytest.raises(ValidationError):
        invocation.connector_id = "other"
    with pytest.raises(ValidationError):
        OpenApiCodeModeInvocation.model_validate(
            {
                **invocation.model_dump(),
                "unexpected": "value",
            }
        )


class EmptyRegistry:
    async def eligible_search_candidates(self, allowed_tool_refs: object) -> list[object]:
        return []


@pytest.mark.asyncio
async def test_execute_openapi_composes_calls_and_redacts_request_values() -> None:
    calls: list[tuple[str, str, dict[str, JsonValue]]] = []

    async def executor(invocation: OpenApiCodeModeInvocation) -> JsonValue:
        calls.append((invocation.connector_id, invocation.operation_id, invocation.query))
        return {"status": "success", "http_status": 200, "response_size_bytes": 2}

    result = await FastMcpMontyCodeModeAdapter(5.0).execute(
        "first = execute_openapi(connector_id='c', operation_id='one', path={}, query={'canary': 'query-secret'}, headers={'X-Key': 'header-secret'}, body={'state': 'missing'})\nsecond = execute_openapi(connector_id='c', operation_id='two', path={}, query={}, headers={}, body={'state': 'present', 'value': {}})\n[first, second]",
        cast(RuntimeConnectorToolRegistry, EmptyRegistry()),
        UnrestrictedConnectorTools(),
        executor,
    )

    assert result.outcome == "success"
    assert "error" not in result.model_dump()
    assert len(calls) == 2
    assert result.final_value == [
        {"status": "success", "http_status": 200, "response_size_bytes": 2},
        {"status": "success", "http_status": 200, "response_size_bytes": 2},
    ]
    assert [call.arguments for call in result.nested_calls] == [
        {"connector_id": "c", "operation_id": "one"},
        {"connector_id": "c", "operation_id": "two"},
    ]
    assert "secret" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_execute_openapi_requires_keyword_only_arguments() -> None:
    async def executor(invocation: OpenApiCodeModeInvocation) -> JsonValue:
        return {}

    result = await FastMcpMontyCodeModeAdapter(5.0).execute(
        "execute_openapi('c', 'one', {}, {}, {}, {'state': 'missing'})",
        cast(RuntimeConnectorToolRegistry, EmptyRegistry()),
        UnrestrictedConnectorTools(),
        executor,
    )

    assert result.outcome == "failure"
    assert result.error == "Code execution failed."


@pytest.mark.asyncio
async def test_execute_openapi_failure_exposes_only_stable_safe_error() -> None:
    async def executor(invocation: OpenApiCodeModeInvocation) -> JsonValue:
        raise RuntimeError("TLS failed for https://example.test/?credential=canary-secret")

    result = await FastMcpMontyCodeModeAdapter(5.0).execute(
        "execute_openapi(connector_id='c', operation_id='one', path={}, query={}, headers={}, body={'state': 'missing'})",
        cast(RuntimeConnectorToolRegistry, EmptyRegistry()),
        UnrestrictedConnectorTools(),
        executor,
    )

    assert result.outcome == "failure"
    assert "final_value" not in result.model_dump()
    assert result.error == "Code execution failed."
    assert "result" not in result.nested_calls[0].model_dump()
    assert result.nested_calls[0].error == "openapi_execution_failed"
    assert "canary-secret" not in result.model_dump_json()
