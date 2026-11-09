import asyncio
from typing import Any
from uuid import uuid4

import pytest
from fastmcp import Client
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import TypeAdapter, ValidationError

from umbod.core.filesystem.models import InputName
from umbod.core.filesystem.namespace import valid_name
from umbod.core.identity_directory.user_models import SearchText

from umbod.core.callers import AuthenticationProvenance
from umbod.mcp.tools.registration import ObservedFunctionTool
from .conftest import FilesystemMcp, caller_snapshot

METADATA = {"content_type": {}, "attributes": {}}
CREATE = "create_filesystem_file"


async def root_id(client: Client) -> str:
    return str((await client.call_tool("get_filesystem_root", {})).data.id)


@pytest.mark.asyncio
async def test_observed_tools_publish_safe_schemas(filesystem_invocation_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        await client.call_tool(CREATE, {"parent_id": await root_id(client), "name": "schema-witness", "metadata": METADATA})
    await filesystem_invocation_mcp.runtime.reconcile()
    tools = await filesystem_invocation_mcp.server.list_tools()
    assert len(tools) == 13
    assert all(isinstance(tool, ObservedFunctionTool) for tool in tools)
    async with Client(filesystem_invocation_mcp.server) as client:
        descriptors = {tool.name: tool for tool in await client.list_tools()}
    assert set(descriptors) == {
        "filesystem_browse", "get_filesystem_root", "get_filesystem_node", "list_filesystem_children",
        "create_filesystem_file", "create_filesystem_directory", "filesystem_upload", "filesystem_delete_file",
        "filesystem_search_sharing_recipients", "filesystem_share", "update_filesystem_node",
        "filesystem_begin_upload", "filesystem_complete_upload",
    }
    assert "Provide at least one of name, parent_id or metadata" in descriptors["update_filesystem_node"].description
    schema = descriptors[CREATE].input_schema
    assert set(schema["properties"]) == {"parent_id", "name", "metadata"}
    assert set(schema["required"]) == {"parent_id", "name", "metadata"}
    assert schema["properties"]["parent_id"]["format"] == "uuid"
    for name, tool in descriptors.items():
        Draft202012Validator.check_schema(tool.input_schema)
        Draft202012Validator.check_schema(tool.output_schema)
        mutation = name.startswith("create_") or name in {
            "filesystem_browse", "filesystem_upload", "filesystem_delete_file", "filesystem_share", "update_filesystem_node",
            "filesystem_begin_upload", "filesystem_complete_upload",
        }
        assert tool.annotations.read_only_hint == (not mutation)
        assert tool.annotations.idempotent_hint == (not mutation or name in {"filesystem_browse", "filesystem_share", "filesystem_complete_upload"})
    assert "content" not in descriptors[CREATE].output_schema["properties"]
    assert "owner" not in descriptors[CREATE].output_schema["properties"]


@pytest.mark.asyncio
async def test_discovery_schemas_validate_filesystem_argument_shapes(
    filesystem_invocation_mcp: FilesystemMcp,
) -> None:
    identifier = str(uuid4())
    base = {"parent_id": identifier, "name": "report.txt", "metadata": METADATA}
    async with Client(filesystem_invocation_mcp.server) as client:
        await client.call_tool(CREATE, {**base, "parent_id": await root_id(client)})
    await filesystem_invocation_mcp.runtime.reconcile()
    async with Client(filesystem_invocation_mcp.server) as client:
        schemas = {tool.name: tool.input_schema for tool in await client.list_tools()}
    valid = {
        "get_filesystem_root": [{}],
        "get_filesystem_node": [{"node_id": identifier}],
        "list_filesystem_children": [{"parent_id": identifier}],
        "create_filesystem_file": [base],
        "create_filesystem_directory": [base],
        "filesystem_upload": [
            {**base, "content": {"encoding": "utf-8", "text": ""}},
            {**base, "content": {"encoding": "base64", "data": "YQ=="}},
        ],
        "filesystem_begin_upload": [{**base, "size_bytes": 0}],
        "filesystem_complete_upload": [{"upload_id": identifier}],
        "filesystem_delete_file": [{"node_id": identifier, "expected_revision": 1}],
        "update_filesystem_node": [
            {"node_id": identifier, "expected_revision": 1, **change}
            for change in ({"name": "renamed"}, {"parent_id": identifier},
                           {"metadata": {"content_type": {}}},
                           {"metadata": {"attributes": {"description": ""}}})
        ],
        "filesystem_browse": [
            {"operation": operation, "target": target}
            for operation in ("ls", "tree", "stat")
            for target in ({"type": "root"}, {"type": "path", "path": "/a//b/"},
                           {"type": "node", "node_id": identifier})
        ] + [{"operation": "home"}],
        "filesystem_search_sharing_recipients": [{"node_id": identifier, "query": " Alice "}],
        "filesystem_share": [
            {"node_id": identifier, "recipient": {"type": kind, key: identifier},
             "permissions": ["read"]}
            for kind, key in (("group", "group_id"), ("user", "user_id"))
        ],
    }
    assert set(valid) == set(schemas)
    for name, arguments in valid.items():
        validator = Draft202012Validator(schemas[name], format_checker=FormatChecker())
        for argument in arguments:
            validator.validate(argument)
    for name in ("create_filesystem_file", "create_filesystem_directory",
                 "filesystem_upload", "filesystem_begin_upload"):
        validator = Draft202012Validator(schemas[name], format_checker=FormatChecker())
        argument = valid[name][0]
        for invalid_name in ("", ".", "..", "a/b", "a\\b", "a\x00b"):
            assert not validator.is_valid({**argument, "name": invalid_name}), (name, invalid_name)
        assert not validator.is_valid({**argument, "parent_id": "not-a-uuid"})
        assert not validator.is_valid({**argument, "metadata": {"content_type": {"value": "text/plain"}, "attributes": {}}})
    assert "anyOf" not in schemas["update_filesystem_node"]
    assert {"name", "parent_id", "metadata"} <= schemas["update_filesystem_node"]["properties"].keys()
    update = Draft202012Validator(schemas["update_filesystem_node"])
    for change in ({}, {"metadata": {}}, {"metadata": {"attributes": {}}}, {"name": ""}):
        assert not update.is_valid({"node_id": identifier, "expected_revision": 1, **change})
    browse = Draft202012Validator(schemas["filesystem_browse"], format_checker=FormatChecker())
    for argument in (
        {"operation": "home", "target": {"type": "root"}},
        {"operation": "stat"},
        {"operation": "stat", "target": {"type": "node", "node_id": "bad"}},
        {"operation": "ls", "target": {"type": "root"}, "max_entries": 0},
        {"operation": "ls", "target": {"type": "root"}, "max_entries": 1001},
        {"operation": "tree", "target": {"type": "root"}, "depth": 17},
        {"operation": "stat", "target": {"type": "path", "path": "relative"}},
    ):
        assert not browse.is_valid(argument)
    upload = Draft202012Validator(schemas["filesystem_upload"])
    for content in ({"encoding": "utf-8", "data": "wrong"},
                    {"encoding": "base64", "text": "wrong"},
                    {"encoding": "other", "text": ""}):
        assert not upload.is_valid({**base, "content": content})
    begin = Draft202012Validator(schemas["filesystem_begin_upload"])
    assert not begin.is_valid({**base, "size_bytes": -1})
    share = Draft202012Validator(schemas["filesystem_share"])
    assert share.is_valid({"node_id": identifier, "group_id": "writers", "permissions": ["read"]})
    assert not share.is_valid({"node_id": identifier, "recipient": {"type": "user", "group_id": "writers"}, "permissions": ["read"]})
    search = Draft202012Validator(schemas["filesystem_search_sharing_recipients"])
    assert not search.is_valid({"node_id": identifier, "query": "   "})


@pytest.mark.parametrize("name", ["", ".", "..", "a/b", "a\\b", "a\x00b", "\ud800", "a", ".hidden", "é", ".\n", "..\n", "a\nb"])
def test_input_name_annotation_preserves_domain_validation(name: str) -> None:
    assert TypeAdapter(InputName).validate_python(name) == name
    schema = TypeAdapter(InputName).json_schema()
    if name != "\ud800":
        assert Draft202012Validator(schema).is_valid(name) == valid_name(name)
    assert "UTF-8" in schema["description"]


def test_search_text_trims_edges_without_collapsing_internal_whitespace() -> None:
    adapter = TypeAdapter(SearchText)
    assert adapter.validate_python("  Alice  Smith  ") == "Alice  Smith"
    padded = " " + "a" * 200 + " "
    assert adapter.validate_python(padded) == "a" * 200
    assert Draft202012Validator(adapter.json_schema()).is_valid(padded)
    with pytest.raises(ValidationError):
        adapter.validate_python("a" * 201)
    with pytest.raises(ValidationError):
        adapter.validate_python(" \t\n ")


@pytest.mark.asyncio
async def test_bootstrap_group_can_create_private_nodes_and_filter_children(
    filesystem_invocation_mcp: FilesystemMcp,
) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        root = await root_id(client)
        created = await client.call_tool(CREATE, {"parent_id": root, "name": "private", "metadata": METADATA})
        child_id = str(created.data.id)
        assert created.data.name == "private"
        assert (await client.call_tool("get_filesystem_node", {"node_id": child_id})).data.id == created.data.id
        filesystem_invocation_mcp.callers.current.set(caller_snapshot(
            "bob", "https://issuer", ("writers",), AuthenticationProvenance.UPSTREAM_VERIFIED
        ))
        listed = await client.call_tool("list_filesystem_children", {"parent_id": root})
        assert listed.structured_content == {"nodes": []}
        denied = await client.call_tool("get_filesystem_node", {"node_id": child_id}, raise_on_error=False)
        missing = await client.call_tool("get_filesystem_node", {"node_id": str(uuid4())}, raise_on_error=False)
        assert denied.content[:1] == missing.content[:1]
        assert denied.meta["computerlove.tech/umbod"]["guidance"] == missing.meta["computerlove.tech/umbod"]["guidance"]
        assert "filesystem_permission_denied" in denied.content[0].text


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["create_filesystem_file", "create_filesystem_directory"])
async def test_creation_is_observed_and_projects_no_storage_keys(
    filesystem_invocation_mcp: FilesystemMcp, tool: str,
) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        root = await root_id(client)
        result = await client.call_tool(tool, {"parent_id": root, "name": "empty", "metadata": METADATA})
        assert set(result.structured_content) == {
            "id", "parent_id", "name", "kind", "metadata", "created_at", "updated_at", "revision", "sharing", "permissions", "visible_to"
        }
    assert any(sample.labels["tool_name"] == tool and sample.labels["outcome"] == "success"
               for sample in filesystem_invocation_mcp.metrics.metric_samples())


@pytest.mark.asyncio
@pytest.mark.parametrize("provenance", [
    AuthenticationProvenance.LOCAL_TEST, AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
    AuthenticationProvenance.LOCAL_SIMULATION, AuthenticationProvenance.LOCAL_SEMANTIC,
])
async def test_nonverified_callers_remain_denied(
    filesystem_invocation_mcp: FilesystemMcp, provenance: AuthenticationProvenance,
) -> None:
    filesystem_invocation_mcp.callers.current.set(caller_snapshot("alice", "https://issuer", ("writers",), provenance))
    async with Client(filesystem_invocation_mcp.server) as client:
        result = await client.call_tool("get_filesystem_root", {}, raise_on_error=False)
    assert result.is_error
    assert "filesystem_permission_denied" in result.content[0].text


@pytest.mark.asyncio
async def test_same_group_identifier_from_other_issuer_has_no_access(filesystem_invocation_mcp: FilesystemMcp) -> None:
    filesystem_invocation_mcp.callers.current.set(caller_snapshot(
        "alice", "https://other-issuer", ("writers",), AuthenticationProvenance.UPSTREAM_VERIFIED
    ))
    async with Client(filesystem_invocation_mcp.server) as client:
        result = await client.call_tool("get_filesystem_root", {}, raise_on_error=False)
    assert result.is_error


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", [
    {"parent_id": "not-a-uuid", "name": "file", "metadata": METADATA},
    {"name": "file"},
    {"name": "file", "metadata": METADATA, "owner": "alice"},
    {"name": "file", "metadata": METADATA, "caller": {}},
    {"name": "file", "metadata": METADATA, "grants": []},
    {"name": "file", "metadata": METADATA, "content": "secret"},
])
async def test_invalid_body_and_authority_injection_are_rejected(
    filesystem_invocation_mcp: FilesystemMcp, arguments: dict[str, Any],
) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        root = await root_id(client)
        result = await client.call_tool(CREATE, {"parent_id": root, **arguments}, raise_on_error=False)
    assert result.is_error


@pytest.mark.asyncio
async def test_filesystem_invalid_names_and_collisions_have_fixed_errors(filesystem_invocation_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        root = await root_id(client)
        invalid = await client.call_tool(CREATE, {"parent_id": root, "name": "../sensitive", "metadata": METADATA}, raise_on_error=False)
        assert invalid.content[0].text == "filesystem_invalid_name: Invalid filesystem name. Use a nonempty UTF-8 name other than . or .., without slashes, backslashes, or null characters."
        await client.call_tool(CREATE, {"parent_id": root, "name": "duplicate", "metadata": METADATA})
        collision = await client.call_tool(CREATE, {"parent_id": root, "name": "duplicate", "metadata": METADATA}, raise_on_error=False)
        assert collision.content[0].text == "filesystem_name_collision: Filesystem name already exists. Inspect the existing node before retrying, or choose a different name."


@pytest.mark.asyncio
async def test_concurrent_callers_and_later_membership_revocation_are_isolated(
    filesystem_invocation_mcp: FilesystemMcp,
) -> None:
    async def invoke(groups: tuple[str, ...]) -> bool:
        filesystem_invocation_mcp.callers.current.set(caller_snapshot(
            "alice", "https://issuer", groups, AuthenticationProvenance.UPSTREAM_VERIFIED
        ))
        async with Client(filesystem_invocation_mcp.server) as client:
            return (await client.call_tool("get_filesystem_root", {}, raise_on_error=False)).is_error

    assert await asyncio.gather(invoke(("writers",)), invoke(())) == [False, True]
    assert await invoke(()) is True
    assert filesystem_invocation_mcp.callers.count == 3
