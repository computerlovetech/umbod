from collections.abc import Sequence

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem.browsing import NodeSummary
from umbod.core.filesystem.sharing import FilesystemSharing, ShareableNodeSharingSummary

from .models import AuthorizedSharingMetadata, FilesystemNodeSummary, RestrictedSharingMetadata


async def enrich_nodes(
    sharing: FilesystemSharing, caller: CallerSnapshot, nodes: Sequence[NodeSummary],
) -> list[FilesystemNodeSummary]:
    node_ids = tuple(dict.fromkeys(node.id for node in nodes))
    summaries = await sharing.summarize_nodes(caller, node_ids)
    indexed = {summary.node_id: summary for summary in summaries.nodes}
    if len(indexed) != len(summaries.nodes) or set(indexed) != set(node_ids):
        raise ValueError("Invalid sharing summary response")
    enriched: list[FilesystemNodeSummary] = []
    for node in nodes:
        summary = indexed[node.id]
        metadata = (
            AuthorizedSharingMetadata(can_share=True, grants=summary.grants)
            if isinstance(summary, ShareableNodeSharingSummary)
            else RestrictedSharingMetadata(can_share=False)
        )
        enriched.append(FilesystemNodeSummary(**node.model_dump(), sharing=metadata))
    return enriched
