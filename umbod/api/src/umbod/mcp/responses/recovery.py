from typing import Any

from umbod.core.responses import OperationState


_CREATE_INSPECTION = (
    "Inspect the original parent with list_filesystem_children or filesystem_browse operation ls, then inspect matching candidates by UUID before creating again.",
    "A truncated listing cannot establish absence. Do not choose a new name merely to bypass an uncertain result.",
)
_UPLOAD_INSPECTION = (
    "If authenticated HTTP inspection is available, inspect GET /api/filesystem/uploads/{upload_id} with the known upload ID and normal authentication, not the transfer capability. There is no MCP upload-status tool.",
    "If the session is uploaded or completed, use filesystem_complete_upload with that same upload_id where authorized; do not begin a replacement or retransfer staged bytes. Deleted files are not restored.",
    "Pending status does not prove that the transfer capability is available. Stop unresolved conflicts or unavailable inspection and contact an administrator with the request reference.",
)
_READ_INSPECTION = (
    "This operation requested no filesystem write. Inspect the failure and current permissions before repeating the read.",
)
_OPERATION_INSTRUCTIONS: dict[str, tuple[str, ...]] = {
    "get_filesystem_root": _READ_INSPECTION,
    "get_filesystem_node": _READ_INSPECTION,
    "list_filesystem_children": _READ_INSPECTION,
    "filesystem_search_sharing_recipients": _READ_INSPECTION,
    "create_filesystem_file": _CREATE_INSPECTION,
    "create_filesystem_directory": _CREATE_INSPECTION,
    "filesystem_upload": (
        "Inspect the original destination using filesystem_browse operation ls before another upload; this inline operation does not expose a recoverable upload ID on failure.",
        "Inspect matching file identity and content as authorized. A truncated listing cannot establish absence; do not upload again merely because the response failed.",
    ),
    "filesystem_complete_upload": _UPLOAD_INSPECTION,
    "update_filesystem_node": (
        "Inspect the original node UUID with get_filesystem_node or filesystem_browse operation stat, even after a rename or move.",
        "Compare requested fields and the current revision before preparing only the remaining authorized changes.",
    ),
    "filesystem_share": (
        "Inspect the original node with filesystem_browse operation stat and review manageable direct grants for the intended recipient and permissions before sharing again.",
        "Restricted or unavailable sharing metadata does not prove that no grants exist. This is not a full effective-access audit; current sharing authority is still required.",
    ),
    "filesystem_delete_file": (
        "Inspect the original UUID with get_filesystem_node or filesystem_browse operation stat before another deletion request. Missing and inaccessible nodes remain indistinguishable and do not prove deletion.",
        "Any fresh deletion attempt requires current eligibility, the current revision, and fresh explicit human confirmation. Do not replay consumed continuation state.",
    ),
    "read_connector_configuration": (
        "No configuration write was requested. Verify the connector reference and current administrator access before repeating read_connector_configuration when the service is available.",
    ),
    "upsert_connector_configuration": (
        "Configuration changes may already have committed before read-back failed. Call read_connector_configuration with the same connector kind and ID.",
        "Compare current settings and revisions with the intended changes; prepare only the remaining authorized changes. Do not replay the original upsert blindly.",
        "If read-back remains unavailable or the connector is absent, stop and contact an administrator with the request reference.",
    ),
}


def _operation_recovery(
    tool_name: str,
    arguments: dict[str, Any],
    error_code: str,
    state: OperationState,
) -> tuple[str, ...]:
    if error_code == "filesystem_delete_approval_denied":
        return (
            "No deletion was authorized by this failed approval. Do not fabricate acceptance, modify continuation state, or replay a consumed continuation.",
            "After decline or cancellation, stop. Only a renewed explicit user request should initiate fresh confirmation.",
        )
    if state == OperationState.NOT_STARTED:
        return ()
    if tool_name == "filesystem_begin_upload":
        session = "A staging session was created" if state == OperationState.COMPLETED else "A staging session may have been created"
        return (
            session + "; file publication is not established. Do not repeat filesystem_begin_upload automatically.",
            "If no upload ID and transfer capability were received, recovery through the existing MCP tools is unavailable. Stop and contact an administrator with the request reference.",
        )
    if tool_name == "filesystem_browse":
        if arguments.get("operation") == "home":
            return (
                "Private home provisioning may already have completed. Inspect the result before deciding whether to repeat the idempotent filesystem_browse operation home; do not substitute an invented path or UUID.",
            )
        return _READ_INSPECTION
    if error_code == "filesystem_upload_receipt_unavailable":
        return (
            "Inspect the known upload session and original destination as authorized. Repeating completion cannot manufacture a verified receipt for a legacy upload.",
            "Stop and contact an administrator with the request reference before starting a replacement upload.",
        )
    if tool_name == "filesystem_complete_upload" and error_code in {
        "filesystem_upload_expired", "filesystem_upload_checksum_mismatch", "filesystem_upload_length_mismatch",
    }:
        return (
            *_UPLOAD_INSPECTION[:1],
            "Inspect the original destination before preparing a corrected replacement session. Declared size and checksum cannot be changed by retrying a transfer; transfer-capability expiry alone does not establish session expiry.",
            "If publication or transfer state cannot be established, stop and contact an administrator with the request reference.",
        )
    return _OPERATION_INSTRUCTIONS.get(tool_name, ())


def recovery_instructions(
    tool_name: str,
    arguments: dict[str, Any],
    error_code: str,
    state: OperationState,
) -> tuple[str, ...]:
    instructions = _operation_recovery(tool_name, arguments, error_code, state)
    if error_code != "filesystem_permission_denied":
        return instructions
    if tool_name in {"create_filesystem_file", "create_filesystem_directory", "filesystem_upload", "filesystem_begin_upload"}:
        return (*instructions,
            "Creating files requires discover and write on the parent directory. Ask its owner for the required permissions, or use filesystem_browse operation home for your private upload destination.",
        )
    return (*instructions,
        "Ask the owner for the permissions required by this operation. Missing and inaccessible nodes remain indistinguishable; do not probe hidden destinations.",
    )
