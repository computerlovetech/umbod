import asyncio
import time
from typing import Any

import httpx
from fastmcp import Client

from test_running_filesystem import tool_payload


async def observed_recipient(client: Client[Any], node_id: str, name: str) -> dict[str, str]:
    deadline = time.monotonic() + 15
    while True:
        result = tool_payload(await client.call_tool("filesystem_search_sharing_recipients", {
            "node_id": node_id, "query": name, "recipient_type": "user",
        }))
        matches = [user for user in result["recipients"] if user["type"] == "user" and user["label"] == name]
        if matches:
            assert len(matches) == 1
            return matches[0]
        assert time.monotonic() < deadline, "Observed recipient did not become searchable"
        await asyncio.sleep(0.1)


async def assert_mcp_user_target_sharing(
    alice: Client[Any], bob: Client[Any], node_id: str, recipient: dict[str, str],
) -> None:
    target = {"type": "user", "user_id": recipient["user_id"]}
    command = {"node_id": node_id, "recipient": target, "permissions": ["discover", "read"]}
    assert tool_payload(await alice.call_tool("filesystem_share", command)) == {**command, "changed": True}
    assert tool_payload(await alice.call_tool("filesystem_share", command)) == {**command, "changed": False}
    inspected = tool_payload(await alice.call_tool("get_filesystem_node", {"node_id": node_id}))
    assert inspected["sharing"] == {
        "can_share": True,
        "grants": [{"recipient": {**target, "label": recipient["label"]}, "permissions": ["discover", "read"]}],
    }
    received = tool_payload(await bob.call_tool("get_filesystem_node", {"node_id": node_id}))
    assert received["id"] == node_id
    assert received["sharing"] == {"can_share": False}


def assert_rest_recipient_scopes(
    alice: httpx.Client, bob: httpx.Client, node_path: str, recipient: dict[str, str],
) -> None:
    group_path = node_path + "/access?recipient_type=group"
    user_path = node_path + "/access?recipient_type=user"
    initial = alice.get(group_path)
    assert initial.status_code == 200, initial.text
    assert initial.json()["grants"] == []
    group = {"recipient": {"type": "group", "group_id": "admin"}, "permissions": ["discover", "read"]}
    assigned = alice.put(group_path, json={"grants": [group]}, headers={"If-Match": initial.headers["etag"]})
    assert assigned.status_code == 200, assigned.text
    combined = alice.get(node_path + "/access")
    groups = alice.get(group_path)
    users = alice.get(user_path)
    for response in (combined, groups, users):
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
    assert combined.headers["etag"] == groups.headers["etag"] == users.headers["etag"]
    assert {grant["recipient"]["type"] for grant in combined.json()["grants"]} == {"group", "user"}
    assert {grant["recipient"]["type"] for grant in groups.json()["grants"]} == {"group"}
    assert users.json()["grants"] == [{
        "recipient": {"type": "user", "user_id": recipient["user_id"], "label": recipient["label"]},
        "permissions": ["discover", "read"],
    }]
    user = {"recipient": {"type": "user", "user_id": recipient["user_id"]}, "permissions": ["discover"]}
    changed = alice.put(user_path, json={"grants": [user]}, headers={"If-Match": users.headers["etag"]})
    assert changed.status_code == 200, changed.text
    assert changed.headers["etag"] != users.headers["etag"]
    assert alice.get(group_path).json()["grants"] == groups.json()["grants"]
    stale = alice.put(group_path, json={"grants": []}, headers={"If-Match": groups.headers["etag"]})
    assert stale.status_code == 412, stale.text
    cleared = alice.put(user_path, json={"grants": []}, headers={"If-Match": changed.headers["etag"]})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["grants"] == []
    assert bob.get(node_path + "/content").status_code == 200
    remaining = alice.get(group_path)
    assert remaining.json()["grants"] == groups.json()["grants"]
    revoked = alice.put(group_path, json={"grants": []}, headers={"If-Match": remaining.headers["etag"]})
    assert revoked.status_code == 200, revoked.text
    assert bob.get(node_path + "/content").status_code == 403
