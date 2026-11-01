from uuid import UUID

from mcp.types import ToolAnnotations

from umbod.core.filesystem.browsing import NodeSummary
from umbod.mcp.tools import McpObservedToolRegistrar
from umbod.mcp.tools.registration import tool_result_is_error

from .authorization import FilesystemToolVisibility
from .browsing import FilesystemBrowseTool
from .deletion import FilesystemDeleteFileTool
from .errors import filesystem_operation
from .models import FilesystemChildren, FilesystemNodeMetadata, FilesystemNodeSummary
from .ports import FilesystemCallerCapture, FilesystemServiceFactory
from .read import FilesystemReadFileTool
from .sharing import enrich_nodes
from .sharing_tools import FilesystemSearchSharingRecipientsTool, FilesystemShareTool
from .upload import FilesystemUploadTool


def register_filesystem_tools(
    registrar: McpObservedToolRegistrar,
    callers: FilesystemCallerCapture,
    services: FilesystemServiceFactory,
    visibility: FilesystemToolVisibility,
) -> None:
    for tool, operation_names in (
        (FilesystemBrowseTool(callers, services), frozenset({"ls", "tree", "stat"})),
        (FilesystemUploadTool(callers, services), frozenset()),
        (FilesystemDeleteFileTool(callers, services), frozenset()),
        (FilesystemReadFileTool(callers, services), frozenset()),
        (FilesystemSearchSharingRecipientsTool(callers, services), frozenset()),
        (FilesystemShareTool(callers, services), frozenset()),
    ):
        tool.auth = visibility.authorize
        registrar.register_tool(tool, result_is_error=tool_result_is_error, operation_names=operation_names)

    async def get_filesystem_root() -> FilesystemNodeSummary:
        with filesystem_operation():
            snapshot = callers.capture()
            node = await services.browsing().get_root(snapshot)
            return (await enrich_nodes(services.sharing(), snapshot, [node]))[0]

    async def get_filesystem_node(node_id: UUID) -> FilesystemNodeSummary:
        with filesystem_operation():
            snapshot = callers.capture()
            node = await services.browsing().get_node(snapshot, node_id)
            return (await enrich_nodes(services.sharing(), snapshot, [node]))[0]

    async def list_filesystem_children(parent_id: UUID) -> FilesystemChildren:
        with filesystem_operation():
            snapshot = callers.capture()
            nodes = await services.browsing().list_children(snapshot, parent_id)
            return FilesystemChildren(nodes=await enrich_nodes(services.sharing(), snapshot, nodes))

    async def create_filesystem_file(
        parent_id: UUID, name: str, metadata: FilesystemNodeMetadata
    ) -> NodeSummary:
        with filesystem_operation():
            snapshot = callers.capture()
            return await services.creation().create_file(snapshot, parent_id, name, metadata)

    async def create_filesystem_directory(
        parent_id: UUID, name: str, metadata: FilesystemNodeMetadata
    ) -> NodeSummary:
        with filesystem_operation():
            snapshot = callers.capture()
            return await services.creation().create_directory(snapshot, parent_id, name, metadata)

    for function, description, readonly in (
        (get_filesystem_root, "Get the provisioned filesystem root.", True),
        (get_filesystem_node, "Get a filesystem node by UUID.", True),
        (list_filesystem_children, "List discoverable children of a directory.", True),
        (create_filesystem_file, "Create an empty private filesystem file.", False),
        (create_filesystem_directory, "Create an empty private filesystem directory.", False),
    ):
        tool = registrar.register(
            function, name=function.__name__, description=(
                description + " Includes manageable direct group sharing only, not a full effective-access audit."
                if readonly else description
            ), auth=visibility.authorize
        )
        tool.annotations = ToolAnnotations(
            readOnlyHint=readonly,
            destructiveHint=False,
            idempotentHint=readonly,
            openWorldHint=False,
        )
