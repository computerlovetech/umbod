from uuid import UUID

from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType
from umbod.infrastructure import create_access_control_driver

from .conftest import FilesystemHttp, create_shared_namespace, replace_shared_access
from .test_browse import create_folder
from .test_content import upload_file
from .test_http_contract import BASE
from .test_sharing_routes import observed_user as observed_user, sharing_http as sharing_http


BOB = {"Authorization": "Bearer bob"}
OUTSIDER = {"Authorization": "Bearer outsider"}
INCOMING = f"{BASE}/shared-with-me"
TEAM = {"type": "group", "group_id": "team"}


def _private_folder(http: FilesystemHttp) -> str:
    root_id = http.client.get(f"{BASE}/browse").json()["node"]["id"]
    return str(create_folder(http, root_id, "Private parent")["id"])


def _replace_grant(
    http: FilesystemHttp, node_id: str, recipient: dict[str, str], *, revoke: bool = False,
) -> None:
    path = f"{BASE}/nodes/{node_id}/access"
    params = {"recipient_type": recipient["type"]}
    current = http.client.get(path, params=params)
    assert current.status_code == 200, current.text
    grants = [] if revoke else [{"recipient": recipient, "permissions": ["discover", "read"], "recursive": True}]
    response = http.client.put(path, params=params, json={"grants": grants}, headers={"If-Match": current.headers["etag"]})
    assert response.status_code == 200, response.text


def test_direct_share_hides_private_parent_and_namespace_location(sharing_http: FilesystemHttp, observed_user: str) -> None:
    client = sharing_http.client
    parent_id = _private_folder(sharing_http)
    uploaded = upload_file(client, f"{BASE}/nodes/{parent_id}/uploads", "Shared file.txt", b"shared contents")
    assert uploaded.status_code == 201
    node_id = uploaded.json()["id"]
    _replace_grant(sharing_http, node_id, {"type": "user", "user_id": observed_user})

    response = client.get(INCOMING, headers=BOB)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert client.get(f"{BASE}/nodes/{parent_id}", headers=BOB).status_code == 403
    direct = client.get(f"{BASE}/nodes/{node_id}", headers=BOB).json()
    assert direct["parent_id"] == parent_id
    assert direct["visible_to"]["type"] == "namespace"
    assert response.json() == {"nodes": [{**direct, "parent_id": {}, "visible_to": {"type": "restricted"}}]}
    assert parent_id not in response.text
    assert direct["visible_to"]["namespace_id"] not in response.text
    assert direct["visible_to"]["name"] not in response.text
    assert client.get(INCOMING, headers=OUTSIDER).json() == {"nodes": []}


def test_matching_user_and_group_grants_deduplicate_and_exclude_owned_nodes(
    sharing_http: FilesystemHttp, observed_user: str,
) -> None:
    node_id = _private_folder(sharing_http)
    _replace_grant(sharing_http, node_id, TEAM)
    _replace_grant(sharing_http, node_id, {"type": "user", "user_id": observed_user})

    recipient = sharing_http.client.get(INCOMING, headers=BOB)
    owner = sharing_http.client.get(INCOMING)

    assert recipient.status_code == owner.status_code == 200
    assert [node["id"] for node in recipient.json()["nodes"]] == [node_id]
    assert owner.json() == {"nodes": []}


def test_recursive_grant_lists_only_explicit_targets(sharing_http: FilesystemHttp) -> None:
    client = sharing_http.client
    folder_id = _private_folder(sharing_http)
    child = create_folder(sharing_http, folder_id, "Inherited child")
    _replace_grant(sharing_http, folder_id, TEAM)

    incoming = client.get(INCOMING, headers=BOB)
    children = client.get(f"{BASE}/nodes/{folder_id}/children", headers=BOB)

    assert incoming.status_code == children.status_code == 200
    assert [node["id"] for node in incoming.json()["nodes"]] == [folder_id]
    assert [node["id"] for node in children.json()["nodes"]] == [child["id"]]


def test_revoked_item_grant_disappears_even_with_namespace_access(sharing_http: FilesystemHttp) -> None:
    client = sharing_http.client
    namespace = create_shared_namespace(sharing_http, "read_write")
    root_id = str(namespace.root_node_id)
    item = create_folder(sharing_http, root_id, "Explicit item share")
    node_id = str(item["id"])
    _replace_grant(sharing_http, node_id, TEAM)
    before = client.get(INCOMING, headers=BOB)
    children = client.get(f"{BASE}/nodes/{root_id}/children", headers=BOB)
    assert before.status_code == children.status_code == 200
    assert before.json() == children.json()
    assert before.json()["nodes"][0]["parent_id"] == root_id
    assert before.json()["nodes"][0]["visible_to"]["namespace_id"] == str(namespace.id)

    _replace_grant(sharing_http, node_id, TEAM, revoke=True)
    after = client.get(INCOMING, headers=BOB)

    assert after.status_code == 200
    assert after.json() == {"nodes": []}
    assert client.get(f"{BASE}/nodes/{node_id}", headers=BOB).status_code == 200


def test_share_in_inaccessible_shared_namespace_hides_its_location(sharing_http: FilesystemHttp, observed_user: str) -> None:
    client = sharing_http.client
    namespace = create_shared_namespace(sharing_http, "read_write")
    root_id = str(namespace.root_node_id)
    node_id = str(create_folder(sharing_http, root_id, "Item share")["id"])
    _replace_grant(sharing_http, node_id, {"type": "user", "user_id": observed_user})
    replace_shared_access(sharing_http, namespace, None)

    response = client.get(INCOMING, headers=BOB)

    assert response.status_code == 200, response.text
    assert client.get(f"{BASE}/nodes/{root_id}", headers=BOB).status_code == 403
    node, = response.json()["nodes"]
    assert node["id"] == node_id
    assert node["parent_id"] == {}
    assert node["visible_to"] == {"type": "restricted"}
    assert root_id not in response.text
    assert str(namespace.id) not in response.text
    assert namespace.name not in response.text


def test_candidates_require_matching_principal_and_effective_discover(sharing_http: FilesystemHttp) -> None:
    driver = create_access_control_driver(database=sharing_http.factories.persistence_runtime.database)
    client = sharing_http.client
    wrong_issuer_id = _private_folder(sharing_http)
    undiscoverable_id = str(create_folder(sharing_http, wrong_issuer_id, "Undiscoverable item")["id"])
    for node_id, issuer, permission in (
        (wrong_issuer_id, "different-issuer", Permission.DISCOVER),
        (undiscoverable_id, "issuer", Permission.READ),
    ):
        client.portal.call(driver.add_grant, AccessGrant(
            node_id=UUID(node_id), principal=Principal(type=PrincipalType.GROUP, issuer=issuer, id="team"),
            permissions={permission}, recursive=False,
        ))

    response = client.get(INCOMING, headers=BOB)

    assert response.status_code == 200, response.text
    assert response.json() == {"nodes": []}
