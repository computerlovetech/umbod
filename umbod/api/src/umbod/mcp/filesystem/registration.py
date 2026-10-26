from uuid import UUID

from mcp.types import ToolAnnotations

from umbod.core.filesystem.browsing import NodeSummary
from umbod.mcp.tools import McpObservedToolRegistrar

from .authorization import root_filesystem_tool_access
from .errors import filesystem_operation
from .models import FilesystemChildren, FilesystemNodeMetadata
from .ports import FilesystemCallerCapture, FilesystemServiceFactory


def register_filesystem_tools(
    registrar: McpObservedToolRegistrar,
    callers: FilesystemCallerCapture,
    services: FilesystemServiceFactory,
) -> None:
    async def get_filesystem_root() -> NodeSummary:
        with filesystem_operation():
            snapshot = callers.capture()
            return await services.browsing().get_root(snapshot)

    async def get_filesystem_node(node_id: UUID) -> NodeSummary:
        with filesystem_operation():
            snapshot = callers.capture()
            return await services.browsing().get_node(snapshot, node_id)

    async def list_filesystem_children(parent_id: UUID) -> FilesystemChildren:
        with filesystem_operation():
            snapshot = callers.capture()
            nodes = await services.browsing().list_children(snapshot, parent_id)
            return FilesystemChildren(nodes=list(nodes))

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
            function, name=function.__name__, description=description, auth=root_filesystem_tool_access
        )
        tool.annotations = ToolAnnotations(
            readOnlyHint=readonly,
            destructiveHint=False,
            idempotentHint=readonly,
            openWorldHint=False,
        )
