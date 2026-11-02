import json
from typing import Any

from mcp.types import ContentBlock, TextContent

from umbod.core.responses import ToolFailureGuidance, ToolFailureMetadata, ToolResponseMetadata


def _guidance_context(metadata: ToolResponseMetadata) -> TextContent:
    guidance = metadata.guidance
    lines = [
        f"Outcome: {guidance.outcome}. Operation state: {guidance.operation_state}.",
        f"Retry advice: {guidance.recovery.retry}.",
        *guidance.recovery.instructions,
        *(f"Notice ({notice.code}): {notice.message}" for notice in guidance.notices),
    ]
    if isinstance(guidance, ToolFailureGuidance):
        lines.append(
            f"Reference: {metadata.request_id}; Umbod server {metadata.server_version} "
            f"(revision {metadata.server_revision})."
        )
    return TextContent(type="text", text="\n".join(lines))


def render_failure_guidance(metadata: ToolFailureMetadata) -> list[TextContent]:
    guidance = metadata.guidance
    summary = f"{guidance.error.code}: {guidance.error.message}"
    if guidance.error.issues:
        summary = summary.rstrip(".") + ". " + " ".join(
            f"{issue.field or 'arguments'}: {issue.correction}"
            for issue in guidance.error.issues
        )
    return [TextContent(type="text", text=summary), _guidance_context(metadata)]


def render_response_guidance(metadata: ToolResponseMetadata) -> list[TextContent]:
    if isinstance(metadata, ToolFailureMetadata):
        return render_failure_guidance(metadata)
    return [_guidance_context(metadata)]


def serialized_payload_content(
    content: list[ContentBlock], payload: dict[str, Any],
) -> list[TextContent]:
    serialized = json.dumps(payload, ensure_ascii=True, allow_nan=False, sort_keys=True)
    for block in content:
        if not isinstance(block, TextContent):
            continue
        try:
            parsed = json.loads(block.text)
            candidate = json.dumps(parsed, ensure_ascii=True, allow_nan=False, sort_keys=True)
        except (ValueError, TypeError):
            continue
        if candidate == serialized:
            return []
    return [TextContent(type="text", text=serialized)]
