import os
import ssl
from contextlib import AsyncExitStack, ExitStack
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastmcp import Client

from conftest import RuntimeEndpoints
from test_running_filesystem import FILESYSTEM, checked_summary, tool_payload, wait_for_filesystem_tools
from test_running_filesystem_homes import NAMESPACE_ADMIN, caller_namespaces
from test_running_personal_mcp_execution import checked, mcp_client, proxy_token

GROUPS = "/api/admin/groups"
MAPPINGS = "/api/admin/system-settings/provider-group-mappings"
DIRECT_GROUP = "members"
ADMIN_GROUP = "admin"


def caller_api(resources: ExitStack, url: str, bearer: str) -> httpx.Client:
    return resources.enter_context(httpx.Client(
        base_url=url, headers={"Authorization": "Bearer " + bearer}, timeout=30,
    ))


def delete_group(admin: httpx.Client, group_id: str) -> None:
    checked(admin.delete(f"{GROUPS}/{group_id}"), 204)


def delete_namespace(admin: httpx.Client, namespace: dict[str, Any]) -> None:
    checked(admin.request("DELETE", f"{NAMESPACE_ADMIN}/{namespace['id']}", json={
        "expected_revision": namespace["revision"], "expected_root_revision": namespace["root_revision"],
    }), 204)


def prepare_membership_namespaces(
    resources: ExitStack, admin: httpx.Client, test_id: str, group_ids: tuple[str, ...],
) -> dict[str, str]:
    registered = {group["group_id"] for group in checked(admin.get(GROUPS))["groups"]}
    roots: dict[str, str] = {}
    for group_id in group_ids:
        if group_id not in registered:
            checked(admin.post(GROUPS, json={"group_id": group_id}), 204)
            resources.callback(delete_group, admin, group_id)
        namespace = checked(admin.post(NAMESPACE_ADMIN, json={
            "name": f"provider-{test_id}-{group_id}", "groups": [{"group_id": group_id, "access": "read"}],
        }), 201)
        resources.callback(delete_namespace, admin, namespace)
        roots[group_id] = namespace["root_node_id"]
    return roots


async def assert_membership_access(
    rest: httpx.Client, mcp: Client[Any], allowed_roots: set[str], denied_roots: set[str],
) -> None:
    rest_namespaces = caller_namespaces(rest)
    browse = tool_payload(await mcp.call_tool("filesystem_browse", {"operation": "namespaces"}))
    assert browse["result"]["namespaces"] == rest_namespaces
    visible_roots = {namespace["root_node_id"] for namespace in rest_namespaces}
    assert allowed_roots <= visible_roots
    assert denied_roots.isdisjoint(visible_roots)

    for root in allowed_roots:
        allowed = checked_summary(rest.get(f"{FILESYSTEM}/nodes/{root}"), 200)
        assert allowed["id"] == root
        assert allowed["permissions"]["can_read"] is True
        inspected = tool_payload(await mcp.call_tool("filesystem_browse", {
            "operation": "stat", "target": {"type": "node", "node_id": root},
        }))["result"]["node"]
        assert inspected["id"] == root
        assert inspected["permissions"] == allowed["permissions"]

    for root in denied_roots:
        assert rest.get(f"{FILESYSTEM}/nodes/{root}").status_code == 403
        denied = await mcp.call_tool("filesystem_browse", {
            "operation": "stat", "target": {"type": "node", "node_id": root},
        }, raise_on_error=False)
        assert denied.is_error
        assert "filesystem_permission_denied" in denied.content[0].text


def mapping(external_value: str, group_id: str) -> dict[str, str]:
    return {"external_value": external_value, "group_id": group_id}


def set_overrides(
    writer: httpx.Client, reader: httpx.Client, mappings: list[dict[str, str]],
) -> None:
    saved = checked(writer.patch(MAPPINGS, json={"operation": "set", "mappings": mappings}))
    assert saved == {"source": "admin_override", "mappings": mappings}
    assert checked(reader.get(MAPPINGS)) == saved


@pytest.mark.asyncio
async def test_provider_group_overrides_change_live_access_across_api_and_mcp_workers(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    member_bearer = os.environ.get("UMBOD_TEST_MEMBER_BEARER_TOKEN")
    if not member_bearer:
        pytest.skip("Requires the runner's signed personal-runtime phase")
    api_urls = (runtime_endpoints.api_base_url, os.environ["UMBOD_TEST_API_B_BASE_URL"])
    mcp_urls = (runtime_endpoints.mcp_url, os.environ["UMBOD_TEST_MCP_B_URL"])
    tls = ssl.create_default_context(cafile=os.environ["UMBOD_TEST_PERSONAL_CA"])
    test_id = uuid4().hex[:12]
    mapped_group = f"mapped-{test_id}"
    admin_bearer = runtime_endpoints.bearer_token
    async with AsyncExitStack() as mcp:
        http = mcp.enter_context(ExitStack())
        primary_admin, secondary_admin = (caller_api(http, url, admin_bearer) for url in api_urls)
        member_apis = [caller_api(http, url, member_bearer) for url in api_urls]
        identity = http.enter_context(httpx.Client(
            base_url=os.environ["UMBOD_TEST_PERSONAL_URL"], verify=tls, timeout=30,
        ))
        roots = prepare_membership_namespaces(http, primary_admin, test_id, (DIRECT_GROUP, mapped_group, ADMIN_GROUP))
        direct_root, mapped_root, admin_root = (roots[group] for group in (DIRECT_GROUP, mapped_group, ADMIN_GROUP))
        original = checked(secondary_admin.get(MAPPINGS))
        assert original["source"] == "inherited_claim_default"
        assert mapping(DIRECT_GROUP, DIRECT_GROUP) in original["mappings"]
        assert checked(primary_admin.get(MAPPINGS)) == original

        member_mcps = [await mcp.enter_async_context(
            mcp_client(url, proxy_token(url, member_bearer, identity)),
        ) for url in mcp_urls]
        public_admin = await mcp.enter_async_context(
            mcp_client(mcp_urls[0], proxy_token(mcp_urls[0], admin_bearer, identity)),
        )
        admin_url = runtime_endpoints.admin_mcp_url
        administrator = await mcp.enter_async_context(
            mcp_client(admin_url, proxy_token(admin_url, admin_bearer, identity)),
        )
        for client in (*member_mcps, public_admin):
            await wait_for_filesystem_tools(client, {"filesystem_browse"})
        member_workers = tuple(zip(member_apis, member_mcps, strict=True))
        for rest, public_mcp in member_workers:
            await assert_membership_access(rest, public_mcp, {direct_root}, {mapped_root, admin_root})
        await assert_membership_access(primary_admin, public_admin, {admin_root}, {direct_root, mapped_root})

        try:
            set_overrides(primary_admin, secondary_admin, [mapping(DIRECT_GROUP, mapped_group)])
            for rest, public_mcp in member_workers:
                await assert_membership_access(rest, public_mcp, {mapped_root}, {direct_root, admin_root})
            await assert_membership_access(primary_admin, public_admin, {admin_root}, {direct_root, mapped_root})

            set_overrides(secondary_admin, primary_admin, [mapping(ADMIN_GROUP, mapped_group)])
            for rest, public_mcp in member_workers:
                await assert_membership_access(rest, public_mcp, {direct_root}, {mapped_root, admin_root})
            await assert_membership_access(primary_admin, public_admin, {mapped_root}, {direct_root, admin_root})
            result = await administrator.call_tool("admin_discover", {"request": {"operation": "list_connectors"}})
            assert result.is_error is False
        finally:
            restored = checked(secondary_admin.patch(MAPPINGS, json={"operation": "reset"}))
        assert restored == original == checked(primary_admin.get(MAPPINGS))
        for rest, public_mcp in member_workers:
            await assert_membership_access(rest, public_mcp, {direct_root}, {mapped_root, admin_root})
        await assert_membership_access(primary_admin, public_admin, {admin_root}, {direct_root, mapped_root})
