import ast
import re
from collections.abc import Awaitable, Callable, Mapping
from inspect import Parameter, Signature
from typing import Any, Literal

from fastmcp.experimental.transforms.code_mode import MontySandboxProvider
from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter

from umbod.mcp.connectors.tools.infrastructure.authorization import (
    ConnectorToolAuthorizationScope,
)
from umbod.mcp.connectors.tools.runtime.registry import RuntimeConnectorToolRegistry


class SuccessfulNestedConnectorCall(BaseModel):
    tool_name: str
    arguments: Mapping[str, Any]
    outcome: Literal["success"] = "success"
    result: Any


class FailedNestedConnectorCall(BaseModel):
    tool_name: str
    arguments: Mapping[str, Any]
    outcome: Literal["failure"] = "failure"
    error: str


NestedConnectorCall = SuccessfulNestedConnectorCall | FailedNestedConnectorCall


class OpenApiNestedCallArguments(BaseModel):
    connector_id: str
    operation_id: str


class OpenApiCodeModeInvocation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    operation_id: str
    path: dict[str, JsonValue]
    query: dict[str, JsonValue]
    headers: dict[str, JsonValue]
    body: JsonValue


class SuccessfulCodeExecution(BaseModel):
    outcome: Literal["success"] = "success"
    final_value: Any
    printed_output: str
    nested_calls: list[NestedConnectorCall]


class FailedCodeExecution(BaseModel):
    outcome: Literal["failure"] = "failure"
    printed_output: str
    error: str
    nested_calls: list[NestedConnectorCall]


class TimedOutCodeExecution(BaseModel):
    outcome: Literal["timeout"] = "timeout"
    printed_output: str
    error: str
    nested_calls: list[NestedConnectorCall]


CodeExecutionResult = SuccessfulCodeExecution | FailedCodeExecution | TimedOutCodeExecution


class _AwaitConnectorCalls(ast.NodeTransformer):
    def __init__(self, tool_names: set[str]) -> None:
        self._tool_names = tool_names

    def visit_Call(self, node: ast.Call) -> ast.AST:
        updated = self.generic_visit(node)
        if (
            isinstance(updated, ast.Call)
            and isinstance(updated.func, ast.Name)
            and updated.func.id in self._tool_names
        ):
            if updated.func.id == "print":
                updated.func.id = (
                    "_codemode_print_empty"
                    if not updated.args and not updated.keywords
                    else "_codemode_print"
                )
            return ast.copy_location(ast.Await(value=updated), updated)
        return updated


OpenApiCodeModeExecutor = Callable[[OpenApiCodeModeInvocation], Awaitable[JsonValue]]

_JSON_VALUE_ADAPTER = TypeAdapter(JsonValue)
_OPENAPI_FUNCTION_NAME = "execute_openapi"


class OpenApiSandboxBinding:
    def bind(
        self,
        executor: OpenApiCodeModeExecutor,
        nested_calls: list[NestedConnectorCall],
    ) -> Any:
        async def call(
            *,
            connector_id: str,
            operation_id: str,
            path: dict[str, JsonValue],
            query: dict[str, JsonValue],
            headers: dict[str, JsonValue],
            body: JsonValue,
        ) -> JsonValue:
            safe_arguments = OpenApiNestedCallArguments(
                connector_id=connector_id,
                operation_id=operation_id,
            ).model_dump()
            try:
                invocation = OpenApiCodeModeInvocation.model_validate(
                    {
                        "connector_id": connector_id,
                        "operation_id": operation_id,
                        "path": path,
                        "query": query,
                        "headers": headers,
                        "body": body,
                    }
                )
                result = _JSON_VALUE_ADAPTER.validate_python(await executor(invocation))
                nested_calls.append(
                    SuccessfulNestedConnectorCall(
                        tool_name=_OPENAPI_FUNCTION_NAME,
                        arguments=safe_arguments,
                        result=result,
                    )
                )
                return result
            except Exception as error:
                safe_error = self._safe_error(error)
                nested_calls.append(
                    FailedNestedConnectorCall(
                        tool_name=_OPENAPI_FUNCTION_NAME,
                        arguments=safe_arguments,
                        error=safe_error,
                    )
                )
                raise RuntimeError(safe_error) from None

        return call

    @staticmethod
    def _safe_error(error: Exception) -> str:
        if _is_timeout_error(error):
            return "openapi_timeout"
        return "openapi_execution_failed"


class FastMcpMontyCodeModeAdapter:
    def __init__(self, timeout_seconds: float) -> None:
        self._sandbox = MontySandboxProvider(limits={"max_duration_secs": timeout_seconds})
        self._openapi_binding = OpenApiSandboxBinding()

    async def execute(
        self,
        code: str,
        registry: RuntimeConnectorToolRegistry,
        authorization_scope: ConnectorToolAuthorizationScope,
        openapi_executor: OpenApiCodeModeExecutor,
    ) -> CodeExecutionResult:
        candidates = await registry.eligible_search_candidates(authorization_scope)
        code_names = {
            candidate.tool_name: self._code_function_name(candidate.tool_name)
            for candidate in candidates
        }
        tool_names = set(code_names.values())
        nested_calls: list[NestedConnectorCall] = []
        printed_lines: list[str] = []

        async def invoke(tool_name: str, **arguments: Any) -> Any:
            try:
                result = await registry.execute_tool(tool_name, arguments, authorization_scope)
                value = result.structured_content
                nested_calls.append(
                    SuccessfulNestedConnectorCall(tool_name=tool_name, arguments={}, result=value)
                )
                return value
            except Exception:
                nested_calls.append(
                    FailedNestedConnectorCall(
                        tool_name=tool_name, arguments={}, error="connector_execution_failed"
                    )
                )
                raise RuntimeError("connector_execution_failed") from None

        external_functions = {
            code_names[candidate.tool_name]: self._bound_invoker(
                invoke, candidate.tool_name, set(candidate.input_schema.get("properties", {}))
            )
            for candidate in candidates
        }

        async def capture_empty_print() -> None:
            printed_lines.append("")

        async def capture_print(value: Any) -> None:
            printed_lines.append(str(value))

        external_functions["_codemode_print_empty"] = capture_empty_print
        external_functions["_codemode_print"] = capture_print
        tool_names.add("print")
        external_functions[_OPENAPI_FUNCTION_NAME] = self._openapi_binding.bind(
            openapi_executor, nested_calls
        )
        tool_names.add(_OPENAPI_FUNCTION_NAME)
        try:
            tree = ast.parse(code)
            transformed = _AwaitConnectorCalls(tool_names).visit(tree)
            ast.fix_missing_locations(transformed)
            final_value = await self._sandbox.run(
                ast.unparse(transformed), external_functions=external_functions
            )
            return SuccessfulCodeExecution(
                final_value=final_value,
                printed_output="".join(f"{line}\n" for line in printed_lines),
                nested_calls=nested_calls,
            )
        except Exception as error:
            printed_output = "".join(f"{line}\n" for line in printed_lines)
            if _is_timeout_error(error):
                return TimedOutCodeExecution(
                    printed_output=printed_output,
                    error="Code execution timed out.",
                    nested_calls=nested_calls,
                )
            return FailedCodeExecution(
                printed_output=printed_output,
                error="Code execution failed.",
                nested_calls=nested_calls,
            )

    @staticmethod
    def _code_function_name(tool_name: str) -> str:
        function_name = re.sub(r"\W", "_", tool_name)
        return function_name if not function_name[0].isdigit() else f"_{function_name}"

    @staticmethod
    def _bound_invoker(invoke: Any, tool_name: str, parameter_names: set[str]) -> Any:
        async def call(**arguments: Any) -> Any:
            return await invoke(tool_name, **arguments)

        call.__signature__ = Signature(
            [Parameter(name, Parameter.KEYWORD_ONLY) for name in parameter_names]
        )
        return call


def _is_timeout_error(error: Exception) -> bool:
    return isinstance(error, TimeoutError) or "time limit exceeded" in str(error).lower()
