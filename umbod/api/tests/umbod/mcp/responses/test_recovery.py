from typing import Any

import pytest

from umbod.core.responses import OperationState, RetryAdvice, ToolErrorDetails, ToolResponseMetadataFactory
from umbod.mcp.responses.recovery import recovery_instructions
from umbod.mcp.responses.rendering import render_response_guidance


@pytest.mark.parametrize(
    ("tool_name", "arguments", "expected"),
    [
        ("get_filesystem_root", {}, "no filesystem write"),
        ("get_filesystem_node", {}, "no filesystem write"),
        ("list_filesystem_children", {}, "no filesystem write"),
        ("filesystem_search_sharing_recipients", {}, "no filesystem write"),
        ("filesystem_browse", {"operation": "stat"}, "no filesystem write"),
        ("filesystem_browse", {"operation": "home"}, "home provisioning"),
        ("create_filesystem_file", {}, "original parent"),
        ("create_filesystem_directory", {}, "original parent"),
        ("filesystem_upload", {}, "original destination"),
        ("filesystem_begin_upload", {}, "staging session was created"),
        ("filesystem_complete_upload", {}, "same upload_id"),
        ("update_filesystem_node", {}, "original node UUID"),
        ("filesystem_share", {}, "manageable direct grants"),
        ("filesystem_delete_file", {}, "fresh explicit human confirmation"),
        ("read_connector_configuration", {}, "No configuration write was requested"),
        ("upsert_connector_configuration", {}, "read_connector_configuration"),
    ],
)
def test_each_builtin_has_safe_model_visible_completed_recovery(
    tool_name: str, arguments: dict[str, Any], expected: str,
) -> None:
    instructions = recovery_instructions(tool_name, arguments, "operation_failed", OperationState.COMPLETED)
    metadata = ToolResponseMetadataFactory("release", "revision").failure(
        "request", error=ToolErrorDetails(code="operation_failed", message="The response failed.", issues=()),
        operation_state=OperationState.COMPLETED, retry=RetryAdvice.INSPECT_BEFORE_RETRY,
        instructions=instructions, notices=(),
    )

    visible = "\n".join(block.text for block in render_response_guidance(metadata))

    assert expected in visible
    assert "Do not retry automatically" in visible
    for instruction in instructions:
        assert instruction in visible


@pytest.mark.parametrize("state", [OperationState.UNKNOWN, OperationState.COMPLETED])
def test_upload_completion_does_not_invent_an_mcp_status_tool(state: OperationState) -> None:
    instructions = recovery_instructions("filesystem_complete_upload", {}, "filesystem_upload_conflict", state)
    text = " ".join(instructions)

    assert "GET /api/filesystem/uploads/{upload_id}" in text
    assert "normal authentication, not the transfer capability" in text
    assert "no MCP upload-status tool" in text
    assert "Pending status does not prove" in text
    assert "same upload_id" in text
    assert "do not begin a replacement" in text


def test_legacy_receipt_failure_does_not_promise_completion_replay_will_repair_it() -> None:
    instructions = recovery_instructions(
        "filesystem_complete_upload", {}, "filesystem_upload_receipt_unavailable", OperationState.UNKNOWN,
    )

    assert "cannot manufacture a verified receipt" in " ".join(instructions)
    assert "same upload_id" not in " ".join(instructions)


def test_pre_admission_argument_failure_does_not_suggest_post_write_recovery() -> None:
    assert recovery_instructions(
        "upsert_connector_configuration", {}, "invalid_arguments", OperationState.NOT_STARTED,
    ) == ()


def test_failed_approval_requires_renewed_user_intent_not_automatic_reconfirmation() -> None:
    text = " ".join(recovery_instructions(
        "filesystem_delete_file", {}, "filesystem_delete_approval_denied", OperationState.NOT_STARTED,
    ))

    assert "No deletion was authorized" in text
    assert "After decline or cancellation, stop" in text
    assert "renewed explicit user request" in text
    assert "Do not fabricate acceptance" in text


@pytest.mark.parametrize("tool_name", ["filesystem_begin_upload", "filesystem_browse", "upsert_connector_configuration"])
def test_recovery_never_reflects_submitted_values_or_unknown_metadata(tool_name: str) -> None:
    instructions = recovery_instructions(
        tool_name,
        {"operation": "secret-operation", "node_id": "secret-destination", "arbitrary-secret-key": "secret-payload"},
        "operation_failed", OperationState.UNKNOWN,
    )

    assert "secret" not in " ".join(instructions)


def test_permission_failure_after_session_creation_retains_staging_recovery() -> None:
    text = " ".join(recovery_instructions(
        "filesystem_begin_upload", {}, "filesystem_permission_denied", OperationState.COMPLETED,
    ))

    assert "A staging session was created" in text
    assert "Do not repeat filesystem_begin_upload automatically" in text
    assert "recovery through the existing MCP tools is unavailable" in text
    assert "discover and write on the parent directory" in text


def test_read_permission_failure_does_not_claim_creation_permissions_are_required() -> None:
    text = " ".join(recovery_instructions(
        "get_filesystem_node", {}, "filesystem_permission_denied", OperationState.UNKNOWN,
    ))

    assert "no filesystem write" in text
    assert "Ask the owner" in text
    assert "Creating files requires" not in text
