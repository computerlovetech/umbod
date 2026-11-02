import asyncio
import json
from typing import Any, Callable, Literal
from uuid import UUID

import pytest
from fastmcp.exceptions import ToolError, ValidationError
from fastmcp.tools.base import Tool, ToolResult
from pydantic import BaseModel, PrivateAttr, ValidationError as ModelValidationError, create_model
from pydantic_core import PydanticCustomError

from umbod.core.responses import RetryAdvice
from umbod.mcp.tools.errors import BuiltinToolArgumentError
from umbod.mcp.filesystem.argument_errors import (
    FilesystemArgumentErrorsTool,
    argument_validation_error,
    argument_json,
    invalid_content_error,
)
from umbod.mcp.filesystem.browsing_models import BROWSE_COMMAND, browse_input_schema
from umbod.mcp.filesystem.sharing_models import SEARCH_RECIPIENTS_COMMAND, SHARE_COMMAND
from umbod.mcp.filesystem.update import UpdateNodeCommand
from umbod.mcp.filesystem.upload_models import UploadCommand
from umbod.mcp.filesystem.upload_session_models import BeginUploadCommand


SENTINEL = "private-payload-sentinel"
NODE_ID = "00000000-0000-0000-0000-000000000001"


class ParsingTool(Tool):
    _parse: Callable[[dict[str, Any]], Any] = PrivateAttr()

    def __init__(self, name: str, schema: dict[str, Any], parse: Callable[[dict[str, Any]], Any]) -> None:
        super().__init__(name=name, parameters=schema)
        self._parse = parse

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        self._parse(arguments)
        return ToolResult(content=[])


class FailingTool(Tool):
    _failure: BaseException = PrivateAttr()

    def __init__(self, failure: BaseException) -> None:
        super().__init__(name="filesystem_upload", parameters={})
        self._failure = failure

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        raise self._failure


def _model_tool(model: type[BaseModel], name: str = "filesystem_upload") -> FilesystemArgumentErrorsTool:
    return FilesystemArgumentErrorsTool(ParsingTool(
        name, model.model_json_schema(), lambda arguments: model.model_validate_json(json.dumps(arguments)),
    ))


@pytest.mark.parametrize(
    ("arguments", "path", "guidance"),
    [
        ({"operation": "tree", "target": {"type": "node", "node_id": SENTINEL}}, "target.node_id", "UUID"),
        ({"operation": "stat", "target": {"type": "path", "path": SENTINEL}}, "target.path", "absolute path"),
        ({"operation": "tree", "target": {"type": "root"}, "depth": 20}, "depth", "1 through 16"),
        ({"operation": "ls", "target": {"type": "root"}, "max_entries": 0}, "max_entries", "1 through 1000"),
        ({"operation": SENTINEL}, "operation", "ls, tree, stat, or home"),
        ({}, "operation", "ls, tree, stat, or home"),
        ({"operation": "stat", "target": {}}, "target.type", "root, path, or node"),
    ],
)
@pytest.mark.asyncio
async def test_browse_errors_use_canonical_paths(
    arguments: dict[str, Any], path: str, guidance: str,
) -> None:
    tool = FilesystemArgumentErrorsTool(ParsingTool(
        "filesystem_browse", browse_input_schema(),
        lambda arguments: BROWSE_COMMAND.validate_json(json.dumps(arguments)),
    ))
    with pytest.raises(ValidationError) as caught:
        await tool.run(arguments)
    message = str(caught.value)
    assert path + ": " in message
    assert guidance in message
    assert SENTINEL not in message
    assert "stat.target" not in message
    assert "tree.target" not in message


@pytest.mark.parametrize("key", [SENTINEL, "name", "content_type", "node_id"])
@pytest.mark.asyncio
async def test_attribute_keys_are_never_rendered(key: str) -> None:
    with pytest.raises(ValidationError) as caught:
        await _model_tool(UploadCommand).run({
            "parent_id": NODE_ID, "name": "file", "metadata": {"attributes": {key: [SENTINEL]}},
            "content": {"encoding": "utf-8", "text": "safe"},
        })
    message = str(caught.value)
    assert "metadata.attributes: " in message
    assert f"attributes.{key}" not in message
    assert SENTINEL not in message


@pytest.mark.parametrize("location", ["root", "metadata", "target"])
@pytest.mark.asyncio
async def test_unknown_fields_report_only_known_parent(location: str) -> None:
    arguments: dict[str, Any] = {"operation": "stat", "target": {"type": "root"}}
    if location == "root":
        arguments[SENTINEL] = {"node_id": SENTINEL}
        expected = "arguments"
    elif location == "target":
        arguments["target"][SENTINEL] = {"node_id": SENTINEL}
        expected = "target"
    else:
        tool = _model_tool(UploadCommand)
        arguments = {
            "parent_id": NODE_ID, "name": "file", "metadata": {SENTINEL: {"content_type": SENTINEL}},
            "content": {"encoding": "utf-8", "text": "safe"},
        }
        expected = "metadata"
    if location != "metadata":
        tool = FilesystemArgumentErrorsTool(ParsingTool(
            "filesystem_browse", browse_input_schema(),
            lambda arguments: BROWSE_COMMAND.validate_json(json.dumps(arguments)),
        ))
    with pytest.raises(ValidationError) as caught:
        await tool.run(arguments)
    assert expected + ": Remove undeclared fields." in str(caught.value)
    assert SENTINEL not in str(caught.value)


@pytest.mark.parametrize("content", [{}, {"encoding": SENTINEL}])
@pytest.mark.asyncio
async def test_missing_or_invalid_content_discriminator_names_declared_field(content: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="content.encoding: Use utf-8 or base64") as caught:
        await _model_tool(UploadCommand).run({
            "parent_id": NODE_ID, "name": "file", "metadata": {}, "content": content,
        })
    assert SENTINEL not in str(caught.value)


@pytest.mark.asyncio
async def test_undiscriminated_union_selects_least_error_root_branch() -> None:
    tool = FilesystemArgumentErrorsTool(ParsingTool(
        "filesystem_share", SHARE_COMMAND.json_schema(),
        lambda arguments: SHARE_COMMAND.validate_json(json.dumps(arguments)),
    ))
    with pytest.raises(ValidationError) as caught:
        await tool.run({"node_id": NODE_ID, "recipient": {}, "permissions": ["read"]})
    message = str(caught.value)
    assert "recipient.type: Use group or user." in message
    assert "group_id:" not in message
    assert "ShareNodeCommand" not in message


@pytest.mark.parametrize("query", ["", " \n ", "x" * 201])
@pytest.mark.asyncio
async def test_search_text_constraints_explain_how_to_correct_the_value(query: str) -> None:
    tool = FilesystemArgumentErrorsTool(ParsingTool(
        "filesystem_search_sharing_recipients", SEARCH_RECIPIENTS_COMMAND.json_schema(),
        lambda arguments: SEARCH_RECIPIENTS_COMMAND.validate_json(json.dumps(arguments)),
    ))
    with pytest.raises(ValidationError) as caught:
        await tool.run({"node_id": NODE_ID, "query": query})
    assert "query: Use nonblank text of at most 200 characters." in str(caught.value)
    assert "schema-declared type" not in str(caught.value)


@pytest.mark.asyncio
async def test_search_union_strips_model_branch_names() -> None:
    tool = FilesystemArgumentErrorsTool(ParsingTool(
        "filesystem_search_sharing_recipients", SEARCH_RECIPIENTS_COMMAND.json_schema(),
        lambda arguments: SEARCH_RECIPIENTS_COMMAND.validate_json(json.dumps(arguments)),
    ))
    with pytest.raises(ValidationError) as caught:
        await tool.run({"node_id": SENTINEL, "query": "person"})
    assert "node_id: Use a valid UUID" in str(caught.value)
    assert "SearchSharingRecipientsCommand" not in str(caught.value)
    assert SENTINEL not in str(caught.value)


@pytest.mark.parametrize(
    ("field", "value", "guidance"),
    [("size_bytes", -1, "actual original byte count"), ("expected_sha256", SENTINEL, "lowercase 64-character")],
)
@pytest.mark.asyncio
async def test_upload_session_guidance_is_actionable(field: str, value: object, guidance: str) -> None:
    arguments = {"parent_id": NODE_ID, "name": "file", "metadata": {}, "size_bytes": 1, field: value}
    with pytest.raises(ValidationError) as caught:
        await _model_tool(BeginUploadCommand).run(arguments)
    assert field + ": " in str(caught.value)
    assert guidance in str(caught.value)
    assert SENTINEL not in str(caught.value)


@pytest.mark.parametrize(
    ("changes", "guidance"),
    [({}, "name, parent_id, or metadata"), ({"metadata": {}}, "attribute or content_type change")],
)
@pytest.mark.asyncio
async def test_empty_update_guidance_names_required_changes(changes: dict[str, Any], guidance: str) -> None:
    with pytest.raises(ValidationError) as caught:
        await _model_tool(UpdateNodeCommand, "update_filesystem_node").run({
            "node_id": NODE_ID, "expected_revision": 1, **changes,
        })
    assert guidance in str(caught.value)


@pytest.mark.asyncio
async def test_many_issues_are_capped_with_fixed_truncation_guidance() -> None:
    model = create_model("ManyFields", **{f"field_{index}": (int, ...) for index in range(12)})
    with pytest.raises(ValidationError) as caught:
        await _model_tool(model).run({})
    message = str(caught.value)
    assert message.count("Provide this required field.") == 8
    assert "Additional issues omitted" in message
    assert "field_8:" not in message
    assert isinstance(caught.value, BuiltinToolArgumentError)
    assert len(caught.value.details.issues) == 8
    assert {issue.reason for issue in caught.value.details.issues} == {"required"}


@pytest.mark.asyncio
async def test_update_metadata_validator_branch_preserves_attribute_field() -> None:
    with pytest.raises(ValidationError) as caught:
        await _model_tool(UpdateNodeCommand, "update_filesystem_node").run({
            "node_id": NODE_ID, "expected_revision": 1,
            "metadata": {"attributes": {SENTINEL: {"node_id": SENTINEL}}},
        })
    message = str(caught.value)
    assert "metadata.attributes: Use an object with string attribute values." in message
    assert "metadata: Use the schema-declared type" not in message
    assert "validate_patch" not in message
    assert "Unchanged" not in message
    assert SENTINEL not in message


def test_duplicate_errors_are_deduplicated_and_validator_details_are_excluded() -> None:
    error = ModelValidationError.from_exception_data(SENTINEL, [
        {"type": PydanticCustomError("value_error", SENTINEL, {"secret": SENTINEL}),
         "loc": ("metadata", "attributes", SENTINEL), "input": SENTINEL}
        for _ in range(3)
    ])
    tool = ParsingTool("filesystem_upload", UploadCommand.model_json_schema(), lambda arguments: arguments)
    failure = argument_validation_error(tool, error)
    message = str(failure)
    assert message.count("metadata.attributes:") == 1
    assert SENTINEL not in message
    assert SENTINEL not in failure.details.model_dump_json()
    assert failure.details.code == "filesystem_invalid_upload"
    assert failure.details.message == "Invalid upload arguments"
    assert len(failure.details.issues) == 1
    assert failure.details.issues[0].field == "metadata.attributes"
    assert failure.details.issues[0].reason == "invalid_value"
    assert failure.retry is RetryAdvice.AFTER_CORRECTION


@pytest.mark.parametrize("failure", [ValidationError(SENTINEL), ToolError(SENTINEL), TypeError(SENTINEL), ValueError(SENTINEL), asyncio.CancelledError()])
@pytest.mark.asyncio
async def test_unrelated_failures_propagate_unchanged(failure: BaseException) -> None:
    with pytest.raises(type(failure)) as caught:
        await FilesystemArgumentErrorsTool(FailingTool(failure)).run({})
    assert caught.value is failure


@pytest.mark.parametrize("value", [{SENTINEL}, float("nan")])
@pytest.mark.asyncio
async def test_json_parsing_failures_use_fixed_guidance(value: object) -> None:
    tool = FilesystemArgumentErrorsTool(ParsingTool(
        "filesystem_upload", {}, lambda arguments: argument_json(arguments, allow_nan=False),
    ))
    with pytest.raises(ValidationError, match="Submit valid JSON") as caught:
        await tool.run({"unknown": value})
    assert SENTINEL not in str(caught.value)
    assert isinstance(caught.value, BuiltinToolArgumentError)
    assert caught.value.details.issues[0].field == "arguments"
    assert caught.value.details.issues[0].reason == "invalid_json"
    assert SENTINEL not in caught.value.details.model_dump_json()


@pytest.mark.asyncio
async def test_function_tool_argument_validation_is_sanitized() -> None:
    async def get_node(node_id: UUID) -> str:
        return str(node_id)

    tool = FilesystemArgumentErrorsTool(Tool.from_function(get_node))
    with pytest.raises(ValidationError) as caught:
        await tool.run({"node_id": SENTINEL})
    assert "node_id: Use a valid UUID" in str(caught.value)
    assert SENTINEL not in str(caught.value)


@pytest.mark.asyncio
async def test_wrapper_preserves_all_base_fields_and_success_results() -> None:
    async def get_node(node_id: UUID) -> str:
        return str(node_id)

    delegate = Tool.from_function(get_node, tags={"filesystem"}, meta={"owner": "filesystem"}, timeout=10)
    wrapper = FilesystemArgumentErrorsTool(delegate)
    assert {name: getattr(wrapper, name) for name in Tool.model_fields} == {
        name: getattr(delegate, name) for name in Tool.model_fields
    }
    assert await wrapper.run({"node_id": NODE_ID}) == await delegate.run({"node_id": NODE_ID})


@pytest.mark.parametrize("schema", [{"$ref": "https://invalid.example/schema"}, {"oneOf": [None]}, {"properties": []}])
def test_malformed_schema_uses_fixed_fallback(schema: dict[str, Any]) -> None:
    error = ModelValidationError.from_exception_data(SENTINEL, [
        {"type": "int_type", "loc": (SENTINEL,), "input": SENTINEL},
    ])
    tool = ParsingTool("filesystem_upload", schema, lambda arguments: arguments)
    message = str(argument_validation_error(tool, error))
    assert "arguments: Use arguments matching the tool input schema." in message
    assert SENTINEL not in message


@pytest.mark.parametrize("encoding", ["utf-8", "base64"])
def test_invalid_content_errors_use_fixed_field_guidance(encoding: Literal["utf-8", "base64"]) -> None:
    failure = invalid_content_error(encoding)
    message = str(failure)
    assert failure.details.code == "filesystem_invalid_upload"
    assert failure.details.issues[0].field == ("content.text" if encoding == "utf-8" else "content.data")
    assert failure.details.issues[0].reason == "invalid_encoding"
    assert message.startswith("filesystem_invalid_upload: Invalid upload arguments. content.")
    assert ("content.text:" if encoding == "utf-8" else "content.data:") in message
