from collections.abc import Mapping
from hashlib import sha256
from functools import partial
from inspect import isawaitable
from typing import Any, cast

from fastmcp.tools import ToolResult

from umbod.core.capabilities import CapabilityIdentity
from umbod.core.invocation import ConnectorInvocationDenied
from umbod.core.connectors.native.runtime.tools import ConnectorToolMapping
from umbod.core.invocation.tools.execution import PreparedToolExecution, ToolExecutionPipeline, ToolExecutionRequest, prepare_tool_execution

from umbod.mcp.connectors.approval import ModernConnectorApprovalRequired
from umbod.mcp.connectors.tools.invocation.arguments import (
    resolve_connector_tool_arguments,
)
from umbod.mcp.connectors.tools.invocation.errors import (
    ConnectorToolErrorFormatter,
    ConnectorToolFailureResult,
)
from umbod.mcp.connectors.tools.definition.naming import _tool_name
from umbod_sdk.connectors.uploaded_file import UploadedFile


def _arguments_without_file_data(arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        name: (
            {
                "filename": value.filename,
                "media_type": value.media_type,
                "size": value.size,
                "sha256": sha256(value.read()).hexdigest(),
            }
            if isinstance(value, UploadedFile)
            else value
        )
        for name, value in arguments.items()
    }


class ConnectorToolInvocationRunner:
    def __init__(
        self,
        mapping: ConnectorToolMapping,
        error_formatter: ConnectorToolErrorFormatter,
        execution_pipeline: ToolExecutionPipeline[ToolResult],
    ) -> None:
        self._mapping = mapping
        self._error_formatter = error_formatter
        self._execution_pipeline = execution_pipeline

    async def invoke(self, arguments: Mapping[str, Any]) -> ToolResult:
        try:
            return await self._execute_connector_tool(arguments)
        except ModernConnectorApprovalRequired as approval:
            return approval.result
        except Exception as error:
            public_error = (
                RuntimeError("Connector invocation denied")
                if isinstance(error, ConnectorInvocationDenied)
                else error
            )
            return ConnectorToolFailureResult(
                content=self._error_formatter.format_error(
                    self._mapping.connector_id,
                    self._mapping.operation_name,
                    public_error,
                ),
            )

    async def _execute_connector_tool(self, arguments: Mapping[str, Any]) -> ToolResult:
        request = ToolExecutionRequest(
            identity=CapabilityIdentity(
                connector_kind="native",
                connector_id=self._mapping.connector_id,
                capability_kind="tool",
                capability_key=self._mapping.operation_name,
            ),
            public_tool_name=_tool_name(self._mapping),
            arguments=_arguments_without_file_data(arguments),
        )
        return await self._execution_pipeline.execute(
            request,
            lambda: self._prepare_execution(arguments),
        )

    async def _prepare_execution(
        self,
        arguments: Mapping[str, Any],
    ) -> PreparedToolExecution[ToolResult]:
        validated_arguments = resolve_connector_tool_arguments(self._mapping.operation, arguments)
        invocation_arguments = (
            _arguments_without_file_data(validated_arguments)
            if any(
                isinstance(value, UploadedFile)
                for value in validated_arguments.values()
            )
            else validated_arguments
        )
        return prepare_tool_execution(
            validated_arguments,
            partial(self._invoke_operation, validated_arguments),
            invocation_arguments=invocation_arguments,
        )

    async def _invoke_operation(self, arguments: Mapping[str, Any]) -> ToolResult:
        operation_result = self._mapping.operation(**arguments)
        if isawaitable(operation_result):
            operation_result = await operation_result
        structured_content = dict(cast(Mapping[str, Any], operation_result))
        return ToolResult(
            structured_content=structured_content,
            meta={
                "connector_id": self._mapping.connector_id,
                "operation_name": self._mapping.operation_name,
            },
        )
