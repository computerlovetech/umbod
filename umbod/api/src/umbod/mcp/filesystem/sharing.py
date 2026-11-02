from collections.abc import Sequence

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem.access import AccessMetadataService, CallerNodeSummary, UnavailableVisibility
from umbod.core.filesystem.authorization import PermissionDenied
from umbod.core.filesystem.errors import PolicyDecodingFailure
from umbod.core.filesystem.browsing import NodeSummary
from umbod.core.filesystem.sharing import FilesystemSharing, ShareableNodeSharingSummary

from .models import AuthorizedSharingMetadata, FilesystemNodeSummary, RestrictedSharingMetadata


async def enrich_nodes(
    sharing: FilesystemSharing, caller: CallerSnapshot, nodes: Sequence[NodeSummary],
    access: AccessMetadataService,
) -> list[FilesystemNodeSummary]:
    projected = await access.enrich_nodes(caller, nodes)
    return await enrich_projected_nodes(sharing, caller, projected)


async def enrich_projected_nodes(
    sharing: FilesystemSharing, caller: CallerSnapshot, nodes: Sequence[CallerNodeSummary],
) -> list[FilesystemNodeSummary]:
    node_ids = tuple(dict.fromkeys(
        node.id for node in nodes if not isinstance(node.visible_to, UnavailableVisibility)
    ))
    indexed = {}
    if node_ids or not nodes:
        try:
            summaries = await sharing.summarize_nodes(caller, node_ids)
        except (PermissionDenied, PolicyDecodingFailure):
            pass
        else:
            indexed = {summary.node_id: summary for summary in summaries.nodes}
            if len(indexed) != len(summaries.nodes) or set(indexed) != set(node_ids):
                raise ValueError("Invalid sharing summary response")
    enriched: list[FilesystemNodeSummary] = []
    for node in nodes:
        summary = indexed.get(node.id)
        metadata = (
            AuthorizedSharingMetadata(can_share=True, grants=summary.grants)
            if isinstance(summary, ShareableNodeSharingSummary)
            else RestrictedSharingMetadata(can_share=False)
        )
        enriched.append(FilesystemNodeSummary(**node.model_dump(), sharing=metadata))
    return enriched
