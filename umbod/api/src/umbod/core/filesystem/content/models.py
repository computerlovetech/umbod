from dataclasses import dataclass

from ..browsing import NodeSummary
from ..ports import ByteStream


@dataclass(frozen=True)
class ContentDownload:
    node: NodeSummary
    data: ByteStream
    size: int
