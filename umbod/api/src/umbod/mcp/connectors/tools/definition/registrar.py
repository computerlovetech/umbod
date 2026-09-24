from typing import Any, Protocol

from fastmcp import FastMCP
from fastmcp.tools import FunctionTool
from fastmcp.tools import ToolResult

from umbod.core.connectors.native.runtime.tools import ConnectorToolMapping
from umbod.core.capabilities.tools.output_schema import PresentConnectorToolOutputSchema

from umbod.mcp.connectors.tools.definition.schema_annotations import (
    connector_tool_annotations,
    connector_tool_signature,
)
from umbod.mcp.connectors.tools.invocation.ports import ConnectorToolInvoker
from umbod.mcp.connectors.tools.definition.naming import _tool_name
from umbod.mcp.connectors.tools.file_app import (
    ConnectorFileAppRegistration,
    FastMcpConnectorFileToolRegistrar,
)
from umbod.mcp.connectors.tools.file_input import uploaded_file_parameter_name


class ConnectorToolRegistrar(Protocol):
    def register(
        self,
        mcp: FastMCP,
        mapping: ConnectorToolMapping,
        invoker: ConnectorToolInvoker,
    ) -> None: ...


def build_connector_tool_definition(
    mapping: ConnectorToolMapping,
    invoker: ConnectorToolInvoker,
) -> FunctionTool:
    async def connector_tool(**arguments: Any) -> ToolResult:
        return await invoker.invoke(arguments)

    output_schema = getattr(mapping, "output_schema", None)
    connector_tool.__signature__ = connector_tool_signature(mapping.operation)
    connector_tool.__annotations__ = connector_tool_annotations(
        mapping.operation, getattr(mapping, "parameters", [])
    )
    tool = FunctionTool.from_function(
        connector_tool,
        name=_tool_name(mapping),
        description=mapping.description,
        tags={"connector", mapping.connector_id},
        output_schema=(
            {"type": "object"}
            if isinstance(output_schema, PresentConnectorToolOutputSchema)
            else None
        ),
        meta={"connector_id": mapping.connector_id, "operation_name": mapping.operation_name},
    )
    if isinstance(output_schema, PresentConnectorToolOutputSchema):
        tool.output_schema = output_schema.output_schema
    return tool


class FastMcpConnectorToolRegistrar:
    def __init__(
        self,
        maximum_uploaded_file_bytes: int,
        file_app_registrations: dict[str, ConnectorFileAppRegistration],
    ) -> None:
        self._maximum_uploaded_file_bytes = maximum_uploaded_file_bytes
        self._file_app_registrations = file_app_registrations

    def register(
        self,
        mcp: FastMCP,
        mapping: ConnectorToolMapping,
        invoker: ConnectorToolInvoker,
    ) -> None:
        if uploaded_file_parameter_name(mapping.operation) is not None:
            FastMcpConnectorFileToolRegistrar(
                self._maximum_uploaded_file_bytes,
                self._file_app_registrations,
            ).register(mcp, mapping, invoker)
            return
        mcp.add_tool(build_connector_tool_definition(mapping, invoker))
