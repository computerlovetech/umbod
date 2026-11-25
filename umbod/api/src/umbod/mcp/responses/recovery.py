from collections.abc import Callable
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
        "Restricted sharing metadata does not establish that no grants exist. Namespace and recursive folder permissions may also apply; current sharing authority is still required.",
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


def _diagnostic_recovery(state: OperationState) -> tuple[str, ...]:
    if state != OperationState.NOT_STARTED:
        return (
                "Persistence may already have committed. Retry only the identical payload with the same idempotency_key; never generate a replacement key. Deduplication makes this exact retry safe, not the generic retry flag.",
                "Do not claim success without a receipt. If the receipt cannot be recovered, contact an administrator with the request reference.",
        )
    return ("Correct the submission before retrying; reload and reassess stale instructions rather than relabeling old evidence.",)


_EARLY_STRATEGIES: dict[str, Callable[[OperationState], tuple[str, ...]]] = {
    "report_diagnostic": _diagnostic_recovery,
}


def _operation_recovery(
    tool_name: str,
    arguments: dict[str, Any],
    error_code: str,
    state: OperationState,
) -> tuple[str, ...]:
    early_strategy = _EARLY_STRATEGIES.get(tool_name)
    if early_strategy is not None:
        return early_strategy(state)
    if error_code == "filesystem_delete_approval_unavailable":
        return ("Only start a new deletion on explicit user request from an MCP client that can deliver the confirmation prompt.",)
    if error_code == "filesystem_delete_approval_denied":
        return (
            "No deletion was authorized by this failed approval. Do not fabricate acceptance, modify continuation state, or replay a consumed continuation.",
            "After decline or cancellation, stop. Only a renewed explicit user request should initiate fresh confirmation.",
        )
    if state == OperationState.NOT_STARTED:
        return ()
    if error_code == "filesystem_upload_receipt_unavailable":
        return (
            "Inspect the known upload session and original destination as authorized. Repeating completion cannot manufacture a verified receipt for a legacy upload.",
            "Stop and contact an administrator with the request reference before starting a replacement upload.",
        )
    strategy = _TOOL_STRATEGIES.get(tool_name)
    if strategy is not None:
        return strategy(arguments, error_code, state)
    return _OPERATION_INSTRUCTIONS.get(tool_name, ())


_NAMESPACE_RECOVERY = "The namespace change may have committed. Call admin_discover with request.operation list_namespaces and check the namespace and revisions before retrying."
_ADMIN_WRITE_RECOVERY = {
    "update_connector_configuration": "The configuration may already have changed. Call admin_inspect with request.operation read_connector_configuration and the same connector reference before retrying.",
    "update_group_permissions": "The grants may already have changed. Call admin_inspect with request.operation read_group_permissions and the same group ID before retrying.",
    "create_namespace": _NAMESPACE_RECOVERY,
    "update_namespace": _NAMESPACE_RECOVERY,
}


def _admin_apply(arguments: dict[str, Any], _error_code: str, _state: OperationState) -> tuple[str, ...]:
    request = arguments.get("request")
    operation = request.get("operation") if isinstance(request, dict) else ""
    key = operation if isinstance(operation, str) else ""
    if key == "update_connector_configuration" and isinstance(request, dict):
        desired_state = request.get("desired_state")
        if isinstance(desired_state, dict) and desired_state.get("operations", []) == []:
            return ("No configuration write was requested. Use admin_inspect with request.operation read_connector_configuration and the same connector reference to read current state.",)
    return (_ADMIN_WRITE_RECOVERY.get(key, "Inspect the target before repeating any administrator write."),)


def _begin_upload(_arguments: dict[str, Any], _error_code: str, state: OperationState) -> tuple[str, ...]:
    session = "A staging session was created" if state == OperationState.COMPLETED else "A staging session may have been created"
    return (
        session + "; file publication is not established. Do not repeat filesystem_begin_upload automatically.",
        "If no upload ID and transfer capability were received, recovery through the existing MCP tools is unavailable. Stop and contact an administrator with the request reference.",
    )


def _browse(arguments: dict[str, Any], _error_code: str, _state: OperationState) -> tuple[str, ...]:
    operation = arguments.get("operation")
    if operation == "namespaces":
        return (
            "Personal namespace provisioning may already have completed. Inspect the result before repeating the idempotent filesystem_browse operation namespaces; use only returned namespace and node IDs.",
        )
    if operation == "home":
        return (
            "Private home provisioning may already have completed. Inspect the result before deciding whether to repeat the idempotent filesystem_browse operation home; do not substitute an invented path or UUID.",
        )
    target = arguments.get("target")
    if isinstance(target, dict) and target.get("type") in ("root", "path"):
        return (
            "Personal namespace provisioning may already have completed. Inspect the current namespace and permissions before repeating this read; root and absolute-path targets select only your personal files.",
        )
    return _READ_INSPECTION


def _complete_upload(_arguments: dict[str, Any], error_code: str, _state: OperationState) -> tuple[str, ...]:
    if error_code in {
        "filesystem_upload_expired", "filesystem_upload_checksum_mismatch", "filesystem_upload_length_mismatch",
    }:
        return (
            *_UPLOAD_INSPECTION[:1],
            "Inspect the original destination before preparing a corrected replacement session. Declared size and checksum cannot be changed by retrying a transfer; transfer-capability expiry alone does not establish session expiry.",
            "If publication or transfer state cannot be established, stop and contact an administrator with the request reference.",
        )
    return _UPLOAD_INSPECTION


RecoveryStrategy = Callable[[dict[str, Any], str, OperationState], tuple[str, ...]]
_TOOL_STRATEGIES: dict[str, RecoveryStrategy] = {
    "admin_apply": _admin_apply,
    "filesystem_begin_upload": _begin_upload,
    "filesystem_browse": _browse,
    "filesystem_complete_upload": _complete_upload,
}


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
            "Creating files requires discover and write on the parent directory. Ask the item owner or a namespace administrator for access, or use filesystem_browse operation home for your private upload destination.",
        )
    return (*instructions,
        "Ask the item owner or a namespace administrator for the permissions required by this operation. Missing and inaccessible nodes remain indistinguishable; do not probe hidden destinations.",
    )
