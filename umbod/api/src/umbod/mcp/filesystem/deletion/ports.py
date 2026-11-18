from enum import Enum
from typing import Protocol, Union

from fastmcp.tools import InputRequiredToolResult

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem.browsing import NodeSummary

from .models import DeleteFileCommand


class FileDeletionApproval(Enum):
    APPROVED = "approved"


class FilesystemDeletionApproval(Protocol):
    async def confirm(
        self, caller: CallerSnapshot, command: DeleteFileCommand, node: NodeSummary,
    ) -> Union[FileDeletionApproval, InputRequiredToolResult]: ...
