from typing import Annotated

from fastapi import Depends

from umbod.core.filesystem.access import AccessMetadataService, CallerNodeSummary
from umbod.core.filesystem.browsing.exploration import BrowseResult

from .deps import get_filesystem_access


Access = Annotated[AccessMetadataService, Depends(get_filesystem_access)]


class CallerBrowseResult(BrowseResult):
    node: CallerNodeSummary
    entries: list[CallerNodeSummary]
