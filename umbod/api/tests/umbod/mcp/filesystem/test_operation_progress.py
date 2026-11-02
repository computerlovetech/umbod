from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from fastmcp.exceptions import ValidationError

from umbod.core.responses import OperationState
from umbod.mcp.filesystem.argument_errors import FilesystemArgumentErrorsTool
from umbod.mcp.filesystem.ports import FilesystemCallerCapture, FilesystemServiceFactory
from umbod.mcp.filesystem.update import FilesystemUpdateNodeTool
from umbod.mcp.filesystem.upload import FilesystemUploadTool
from umbod.mcp.filesystem.upload_sessions import FilesystemBeginUploadTool, FilesystemCompleteUploadTool
from umbod.mcp.responses.progress import operation_progress_context
from umbod.mcp.tools.errors import BuiltinToolError


NODE_ID = "00000000-0000-0000-0000-000000000001"


@pytest.mark.parametrize(
    ("tool_type", "service_name", "mutation", "arguments"),
    [
        (FilesystemUploadTool, "uploads", "complete", {
            "parent_id": NODE_ID, "name": "file", "metadata": {"content_type": {}, "attributes": {}},
            "content": {"encoding": "utf-8", "text": "safe"},
        }),
        (FilesystemBeginUploadTool, "upload_sessions", "begin_delegated", {
            "parent_id": NODE_ID, "name": "file", "metadata": {"content_type": {}, "attributes": {}}, "size_bytes": 4,
        }),
        (FilesystemCompleteUploadTool, "upload_sessions", "complete_verified", {"upload_id": NODE_ID}),
        (FilesystemUpdateNodeTool, "updates", "update_node", {
            "node_id": NODE_ID, "expected_revision": 1, "name": "renamed",
        }),
    ],
)
@pytest.mark.asyncio
async def test_mutation_return_marks_completed_before_result_processing(
    tool_type: type[FilesystemUploadTool] | type[FilesystemBeginUploadTool] | type[FilesystemCompleteUploadTool] | type[FilesystemUpdateNodeTool],
    service_name: str, mutation: str, arguments: dict[str, Any],
) -> None:
    callers = Mock(spec=FilesystemCallerCapture)
    services = Mock(spec=FilesystemServiceFactory)
    services.upload_api_origin.return_value = "https://api.example.test"
    service = Mock()
    service.begin = AsyncMock(return_value=Mock())
    service.put = AsyncMock()
    committed_result = Mock()
    committed_result.node = Mock()
    committed_result.receipt = Mock()
    committed_result.session = Mock()
    committed_result.session.id = "invalid-result"
    setattr(service, mutation, AsyncMock(return_value=committed_result))
    getattr(services, service_name).return_value = service
    services.access.side_effect = RuntimeError("SECRET enrichment failed")
    services.sharing.side_effect = RuntimeError("SECRET enrichment failed")
    tool = tool_type(callers, services)
    with operation_progress_context() as progress:
        with pytest.raises(BuiltinToolError):
            await tool.run(arguments)
        assert progress.state is OperationState.COMPLETED
    getattr(service, mutation).assert_awaited_once()


@pytest.mark.asyncio
async def test_argument_failure_before_business_scope_remains_not_started() -> None:
    callers = Mock(spec=FilesystemCallerCapture)
    services = Mock(spec=FilesystemServiceFactory)
    tool = FilesystemArgumentErrorsTool(FilesystemCompleteUploadTool(callers, services))
    with operation_progress_context() as progress:
        with pytest.raises(ValidationError):
            await tool.run({"upload_id": "SECRET"})
        assert progress.state is OperationState.NOT_STARTED
    callers.capture.assert_not_called()
    services.upload_sessions.assert_not_called()
