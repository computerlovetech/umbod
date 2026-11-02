from uuid import uuid4

from fastmcp.exceptions import ToolError, ValidationError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools import InputRequiredToolResult, ToolResult
from mcp.types import CallToolRequestParams, CallToolResult, TextContent

from umbod.build_identity import UMBOD_RELEASE, UMBOD_REVISION
from umbod.http_metadata import current_request_id, request_id_context
from umbod.mcp.responses.adapter import BuiltinToolResult, RESPONSE_METADATA_KEY


class McpResponseMetadataMiddleware(Middleware):
    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        request_id = current_request_id() or uuid4().hex
        with request_id_context(request_id):
            try:
                result = await call_next(context)
            except (ToolError, ValidationError) as error:
                result = ToolResult(content=[TextContent(type="text", text=str(error))], is_error=True)
            if isinstance(result, InputRequiredToolResult):
                return result
            metadata = result.meta[RESPONSE_METADATA_KEY] if isinstance(result, BuiltinToolResult) else {
                "server_version": UMBOD_RELEASE,
                "server_revision": UMBOD_REVISION,
                "request_id": request_id,
            }
            wire_result = result.to_mcp_result()
            if isinstance(wire_result, CallToolResult):
                response = wire_result.model_copy(update={
                    "meta": {**(wire_result.meta or {}), RESPONSE_METADATA_KEY: metadata},
                })
                if response.is_error and not isinstance(result, BuiltinToolResult):
                    response = response.model_copy(update={
                        "content": [*response.content, self._error_context(request_id)],
                    })
                return ToolResult.from_mcp_result(response)
            return result.model_copy(update={
                "meta": {**(result.meta or {}), RESPONSE_METADATA_KEY: metadata},
            })

    def _error_context(self, request_id: str) -> TextContent:
        return TextContent(
            type="text",
            text=f"Umbod server {UMBOD_RELEASE} (revision {UMBOD_REVISION}); request ID {request_id}.",
        )
