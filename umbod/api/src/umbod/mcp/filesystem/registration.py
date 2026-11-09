from uuid import UUID

from fastmcp.tools import FunctionTool
from fastmcp.tools.base import ToolResult
from mcp.types import ToolAnnotations

from umbod.core.filesystem.models import InputName
from umbod.mcp.tools import McpObservedToolRegistrar
from umbod.mcp.tools.registration import tool_result_is_error

from .argument_errors import FilesystemArgumentErrorsTool
from .authorization import FilesystemToolVisibility
from .browsing import FilesystemBrowseTool
from .deletion import FilesystemDeleteFileTool
from umbod.mcp.responses.progress import operation_completed

from .errors import filesystem_operation
from .links import file_link_result
from .models import FilesystemChildren, FilesystemNodeMetadata, FilesystemNodeSummary
from .ports import FilesystemCallerCapture, FilesystemDeletionApproval, FilesystemServiceFactory
from .sharing import enrich_nodes
from .sharing_tools import FilesystemSearchSharingRecipientsTool, FilesystemShareTool
from .update import FilesystemUpdateNodeTool
from .upload import FilesystemUploadTool
from .upload_sessions import FilesystemBeginUploadTool, FilesystemCompleteUploadTool


def register_filesystem_tools(
    registrar: McpObservedToolRegistrar,
    callers: FilesystemCallerCapture,
    services: FilesystemServiceFactory,
    visibility: FilesystemToolVisibility,
    deletion_approval: FilesystemDeletionApproval,
) -> None:
    for tool, operation_names in (
        (FilesystemBrowseTool(callers, services), frozenset({"ls", "tree", "stat", "home"})),
        (FilesystemUploadTool(callers, services), frozenset()),
        (FilesystemBeginUploadTool(callers, services), frozenset()),
        (FilesystemCompleteUploadTool(callers, services), frozenset()),
        (FilesystemUpdateNodeTool(callers, services), frozenset()),
        (FilesystemDeleteFileTool(callers, services, deletion_approval), frozenset()),
        (FilesystemSearchSharingRecipientsTool(callers, services), frozenset()),
        (FilesystemShareTool(callers, services), frozenset()),
    ):
        tool.auth = visibility.authorize
        registrar.register_tool(
            FilesystemArgumentErrorsTool(tool), result_is_error=tool_result_is_error,
            operation_names=operation_names, builtin_response=True,
        )

    async def get_filesystem_root() -> ToolResult:
        with filesystem_operation():
            snapshot = callers.capture()
            node = await services.browsing().get_root(snapshot)
            operation_completed()
            result = (await enrich_nodes(services.sharing(), snapshot, [node], services.access()))[0]
            return file_link_result(result, [result], result.model_dump_json())

    async def get_filesystem_node(node_id: UUID) -> ToolResult:
        with filesystem_operation():
            snapshot = callers.capture()
            node = await services.browsing().get_node(snapshot, node_id)
            operation_completed()
            result = (await enrich_nodes(services.sharing(), snapshot, [node], services.access()))[0]
            return file_link_result(result, [result], result.model_dump_json())

    async def list_filesystem_children(parent_id: UUID) -> ToolResult:
        with filesystem_operation():
            snapshot = callers.capture()
            nodes = await services.browsing().list_children(snapshot, parent_id)
            operation_completed()
            result = FilesystemChildren(nodes=await enrich_nodes(services.sharing(), snapshot, nodes, services.access()))
            return file_link_result(result, result.nodes, result.model_dump_json())

    async def create_filesystem_file(
        parent_id: UUID, name: InputName, metadata: FilesystemNodeMetadata
    ) -> ToolResult:
        with filesystem_operation():
            snapshot = callers.capture()
            node = await services.creation().create_file(snapshot, parent_id, name, metadata)
            operation_completed()
            result = (await enrich_nodes(services.sharing(), snapshot, [node], services.access()))[0]
            return file_link_result(result, [result], result.model_dump_json())

    async def create_filesystem_directory(
        parent_id: UUID, name: InputName, metadata: FilesystemNodeMetadata
    ) -> FilesystemNodeSummary:
        with filesystem_operation():
            snapshot = callers.capture()
            node = await services.creation().create_directory(snapshot, parent_id, name, metadata)
            operation_completed()
            return (await enrich_nodes(services.sharing(), snapshot, [node], services.access()))[0]

    for function, description, readonly, output_model in (
        (get_filesystem_root, "Get the provisioned filesystem root.", True, FilesystemNodeSummary),
        (get_filesystem_node, "Get a filesystem node by UUID with an MCP resource link for files.", True, FilesystemNodeSummary),
        (list_filesystem_children, "List discoverable children with MCP resource links for files.", True, FilesystemChildren),
        (create_filesystem_file, "Create an empty private filesystem file and return its MCP resource link.", False, FilesystemNodeSummary),
        (create_filesystem_directory, "Create an empty private filesystem directory.", False, FilesystemNodeSummary),
    ):
        tool = FunctionTool.from_function(
            function, name=function.__name__, description=(
                description + " Includes manageable direct group and user sharing only, not a full effective-access audit."
                if readonly else description
            ), auth=visibility.authorize, tags=set(), meta={},
        )
        tool.output_schema = output_model.model_json_schema()
        tool.annotations = ToolAnnotations(
            readOnlyHint=readonly,
            destructiveHint=False,
            idempotentHint=readonly,
            openWorldHint=False,
        )
        registrar.register_tool(
            FilesystemArgumentErrorsTool(tool), result_is_error=tool_result_is_error,
            operation_names=frozenset(), builtin_response=True,
        )
