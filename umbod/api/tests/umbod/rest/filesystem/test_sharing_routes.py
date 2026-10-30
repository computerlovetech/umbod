from unittest.mock import create_autospec
from uuid import UUID, uuid4

import pytest

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType
from umbod.core.filesystem.authorization import FilesystemIdentityResolver
from umbod.core.filesystem.sharing import (
    EligibleSharingGroup, EligibleSharingGroups,
    FilesystemSharing, InvalidSharingPolicy, SharingPolicyUnavailable,
    NodeGroupPolicyView, ReplaceNodeGroupPolicy,
)
from umbod.core.persistence import Database, TransactionMode
from umbod.core.groups import RegisterGroupMetadata
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.groups.stores.registration import register_group_in_session
from umbod.infrastructure import create_access_control_driver
from umbod.rest.authentication.authorization import JwtClaims, JwtVerificationError
from umbod.rest.authentication.verifiers import SimulatedJwtVerifier
from umbod.rest.filesystem import deps
from umbod.rest.filesystem.deps import get_filesystem_sharing

from .conftest import FilesystemHttp
from .test_http_contract import BASE, BODY

OPAQUE = '"' + "a" * 64 + '"'


@pytest.fixture
def sharing_http(filesystem_http: FilesystemHttp) -> FilesystemHttp:
    filesystem_http.factories.settings.oidc.issuer_url = "issuer"
    filesystem_http.factories.settings.admin_authentication.mode = "jwt"
    return filesystem_http


@pytest.fixture
def private_node(sharing_http: FilesystemHttp) -> dict[str, object]:
    root = sharing_http.client.get(BASE + "/root").json()
    response = sharing_http.client.post(f"{BASE}/nodes/{root['id']}/directories", json=BODY)
    assert response.status_code == 201
    return response.json()


def access_path(node: dict[str, object]) -> str:
    return f"{BASE}/nodes/{node['id']}/access"


def register_recipient(http: FilesystemHttp, group_id: str) -> None:
    async def register() -> None:
        async with http.factories.persistence_runtime.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await register_group_in_session(session, group_id)

    http.client.portal.call(register)


def grant_recipient(http: FilesystemHttp, node: dict[str, object], permissions: set[Permission]) -> None:
    driver = create_access_control_driver(database=http.factories.persistence_runtime.database)
    http.client.portal.call(driver.add_grant, AccessGrant(
        node_id=UUID(str(node["id"])),
        principal=Principal(type=PrincipalType.GROUP, issuer="issuer", id="team"),
        permissions=permissions, recursive=False,
    ))


def test_owner_can_replace_and_revoke_with_authoritative_etag_without_content_changes(
    sharing_http: FilesystemHttp, private_node: dict[str, object],
) -> None:
    client = sharing_http.client
    path = access_path(private_node)
    initial = client.get(path)
    assert initial.status_code == 200, initial.text
    assert set(initial.json()) == {"node_id", "revision", "groups", "blocked_group_ids"}
    assert initial.json()["groups"] == []
    assert initial.headers["etag"] == '"' + initial.json()["revision"] + '"'
    groups = [{"group_id": "team", "permissions": ["discover", "share"]}]
    saved = client.put(path, json={"groups": groups}, headers={"If-Match": initial.headers["etag"]})
    assert saved.status_code == 200, saved.text
    assert saved.headers["etag"] != initial.headers["etag"]
    assert saved.json() == client.get(path).json()
    assert set(saved.json()["groups"][0]["permissions"]) == {"discover", "share"}
    assert client.get(f"{BASE}/nodes/{private_node['id']}").json() == private_node
    bob = {"Authorization": "Bearer bob"}
    assert client.get(path, headers=bob).status_code == 200
    revoked = client.put(path, json={"groups": []}, headers={**bob, "If-Match": saved.headers["etag"]})
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["groups"] == []
    assert client.get(path, headers=bob).status_code == 403
    stale = client.put(path, json={"groups": groups}, headers={"If-Match": saved.headers["etag"]})
    assert stale.status_code == 412
    for response in (initial, saved, revoked, stale):
        assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("permissions", [{Permission.DISCOVER}, {Permission.SHARE}, set()])
@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_missing_discover_or_share_denies_before_stale_revision_and_unknown_recipient(
    sharing_http: FilesystemHttp, private_node: dict[str, object], permissions: set[Permission], method: str,
) -> None:
    if permissions:
        grant_recipient(sharing_http, private_node, permissions)
    headers = {"Authorization": "Bearer bob", "If-Match": OPAQUE}
    body = {"groups": [{"group_id": "secret-unregistered", "permissions": ["read"]}]}
    denied = sharing_http.client.request(method, access_path(private_node), json=body, headers=headers)
    missing = sharing_http.client.request(method, f"{BASE}/nodes/{uuid4()}/access", json=body, headers=headers)
    assert denied.status_code == missing.status_code == 403
    assert denied.json() == missing.json()
    assert "secret" not in denied.text


@pytest.mark.parametrize("header", ["", "*", 'W/"abc"', "abc", '""', '"1"', '"abc", "def"'])
def test_sharing_preconditions_are_not_content_revisions(
    sharing_http: FilesystemHttp, private_node: dict[str, object], header: str,
) -> None:
    response = sharing_http.client.put(access_path(private_node), json={"groups": []}, headers={"If-Match": header})
    assert response.status_code == 422


def test_sharing_requires_precondition_and_rejects_multiple_headers(
    sharing_http: FilesystemHttp, private_node: dict[str, object],
) -> None:
    path = access_path(private_node)
    assert sharing_http.client.put(path, json={"groups": []}).status_code == 428
    response = sharing_http.client.put(path, json={"groups": []}, headers=[("If-Match", OPAQUE), ("If-Match", OPAQUE)])
    assert response.status_code == 422


@pytest.mark.parametrize("body", [
    {"grants": []}, {"groups": [], "issuer": "evil"}, {"groups": [], "users": []},
    {"groups": [], "recursive": True}, {"groups": [], "expected_revision": "abc"},
    {"groups": [{"group_id": "team", "permissions": ["read"], "issuer": "evil"}]},
    {"groups": [{"group_id": "team", "permissions": ["read"], "recursive": True}]},
    {"groups": [{"group_id": "team", "permissions": []}]},
    {"groups": [{"group_id": " ", "permissions": ["read"]}]},
    {"groups": [{"group_id": "team", "permissions": ["read"]}] * 2},
])
def test_group_only_request_rejects_obsolete_or_extra_authority_without_writes(
    sharing_http: FilesystemHttp, private_node: dict[str, object], body: dict[str, object],
) -> None:
    path = access_path(private_node)
    before = sharing_http.client.get(path)
    response = sharing_http.client.put(path, json=body, headers={"If-Match": before.headers["etag"]})
    assert response.status_code == 422
    assert sharing_http.client.get(path).json() == before.json()


def test_group_ids_are_exact_registered_recipients_without_automatic_creation(
    sharing_http: FilesystemHttp, private_node: dict[str, object],
) -> None:
    register_recipient(sharing_http, " Exact ")
    path = access_path(private_node)
    initial = sharing_http.client.get(path)
    rejected = sharing_http.client.put(path, json={"groups": [{"group_id": "Exact", "permissions": ["read"]}]}, headers={"If-Match": initial.headers["etag"]})
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "filesystem_sharing_invalid"
    assert "Exact" not in rejected.text
    assert sharing_http.client.get(path).json() == initial.json()
    accepted = sharing_http.client.put(path, json={"groups": [{"group_id": " Exact ", "permissions": ["read"]}]}, headers={"If-Match": initial.headers["etag"]})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["groups"][0]["group_id"] == " Exact "


@pytest.mark.parametrize("error,status,code", [
    (InvalidSharingPolicy("private group state"), 422, "filesystem_sharing_invalid"),
    (SharingPolicyUnavailable("private issuer"), 503, "filesystem_policy_unavailable"),
])
def test_domain_errors_are_sanitized(
    sharing_http: FilesystemHttp, error: Exception, status: int, code: str,
) -> None:
    service = create_autospec(FilesystemSharing, instance=True)
    service.inspect.side_effect = error

    def provide() -> FilesystemSharing:
        return service

    sharing_http.app.dependency_overrides[get_filesystem_sharing] = provide
    response = sharing_http.client.get(f"{BASE}/nodes/{uuid4()}/access")
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    assert "private" not in response.text
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("configured_issuer,local,expected_issuer", [
    (" Exact Issuer ", False, " Exact Issuer "), ("", True, "urn:umbod:local"),
])
def test_sharing_factory_is_request_scoped_with_exact_configured_issuer(
    sharing_http: FilesystemHttp, private_node: dict[str, object], monkeypatch: pytest.MonkeyPatch,
    configured_issuer: str, local: bool, expected_issuer: str,
) -> None:
    sharing_http.factories.settings.oidc.issuer_url = configured_issuer
    if local:
        sharing_http.factories.settings.admin_authentication.mode = "simulation"
    services: list[FilesystemSharing] = []
    factory = deps.create_filesystem_sharing

    def track(*, database: Database, resolver: FilesystemIdentityResolver, issuer: str) -> FilesystemSharing:
        assert issuer == expected_issuer
        assert database is sharing_http.factories.persistence_runtime.database
        service = factory(database=database, resolver=resolver, issuer=issuer)
        services.append(service)
        return service

    monkeypatch.setattr(deps, "create_filesystem_sharing", track)
    assert sharing_http.client.get(access_path(private_node)).status_code == 200
    assert sharing_http.client.get(access_path(private_node)).status_code == 200
    assert services[0] is not services[1]


@pytest.mark.parametrize("issuer", ["", "   "])
def test_blank_configured_issuer_fails_closed(sharing_http: FilesystemHttp, issuer: str) -> None:
    sharing_http.factories.settings.oidc.issuer_url = issuer
    response = sharing_http.client.get(f"{BASE}/nodes/{uuid4()}/access")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "filesystem_policy_unavailable"


def test_replacement_preserves_foreign_user_and_recursive_grants(
    sharing_http: FilesystemHttp, private_node: dict[str, object],
) -> None:
    driver = create_access_control_driver(database=sharing_http.factories.persistence_runtime.database)
    identifier = UUID(str(private_node["id"]))
    protected = [AccessGrant(
        node_id=identifier,
        principal=Principal(type=kind, issuer=issuer, id=group_id),
        permissions={Permission.READ}, recursive=recursive,
    ) for kind, issuer, group_id, recursive in (
        (PrincipalType.USER, "issuer", "bob", False),
        (PrincipalType.GROUP, "foreign", "team", False),
        (PrincipalType.GROUP, "issuer", "team", True),
    )]
    for grant in protected:
        sharing_http.client.portal.call(driver.add_grant, grant)
    path = access_path(private_node)
    initial = sharing_http.client.get(path)
    assert initial.json()["groups"] == []
    assert initial.json()["blocked_group_ids"] == ["team"]
    collision = sharing_http.client.put(path, json={"groups": [{"group_id": "team", "permissions": ["read"]}]}, headers={"If-Match": initial.headers["etag"]})
    assert collision.status_code == 422
    revoked = sharing_http.client.put(path, json={"groups": []}, headers={"If-Match": initial.headers["etag"]})
    assert revoked.status_code == 200
    assert revoked.json() == initial.json()
    stored = sharing_http.client.portal.call(driver.list_grants, identifier)
    assert len(stored) == len(protected)
    assert all(grant in stored for grant in protected)


def test_nonadmin_owner_can_select_registered_groups_without_admin_catalogue_access(
    sharing_http: FilesystemHttp, private_node: dict[str, object], monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_admin_token(self: SimulatedJwtVerifier, token: str) -> JwtClaims:
        raise JwtVerificationError()

    monkeypatch.setattr(SimulatedJwtVerifier, "verify", reject_admin_token)
    management = create_group_management(sharing_http.factories.persistence_runtime.database)
    sharing_http.client.portal.call(management.register_group_metadata, RegisterGroupMetadata(
        group_id=" Exact ", label="Display label", description="Managed collaboration",
    ))
    path = access_path(private_node)
    eligible = sharing_http.client.get(path + "/eligible-groups")
    assert eligible.status_code == 200, eligible.text
    assert eligible.json() == {"groups": [
        {"group_id": " Exact ", "label": "Display label", "description": "Managed collaboration"},
        {"group_id": "team", "label": "team", "description": ""},
    ]}
    assert sharing_http.client.get("/api/admin/groups").status_code in (401, 403)
    assert sharing_http.client.get("/api/me/groups").status_code == 404
    grant_recipient(sharing_http, private_node, {Permission.DISCOVER, Permission.SHARE})
    assert sharing_http.client.get(path + "/eligible-groups", headers={"Authorization": "Bearer bob"}).json() == eligible.json()


@pytest.mark.parametrize("permissions", [set(), {Permission.DISCOVER}, {Permission.SHARE}])
def test_eligible_groups_requires_both_permissions_and_hides_missing_target(
    sharing_http: FilesystemHttp, private_node: dict[str, object], permissions: set[Permission],
) -> None:
    if permissions:
        grant_recipient(sharing_http, private_node, permissions)
    headers = {"Authorization": "Bearer bob"}
    hidden = sharing_http.client.get(access_path(private_node) + "/eligible-groups", headers=headers)
    missing = sharing_http.client.get(f"{BASE}/nodes/{uuid4()}/access/eligible-groups", headers=headers)
    assert hidden.status_code == missing.status_code == 403
    assert hidden.json() == missing.json()
    assert "team" not in hidden.text


class RecordingSharing:
    def __init__(self, node_id: UUID) -> None:
        self.view = NodeGroupPolicyView(node_id=node_id, revision="before", groups=(), blocked_group_ids=())
        self.commands: list[ReplaceNodeGroupPolicy] = []

    async def eligible_groups(self, snapshot: CallerSnapshot, node_id: UUID) -> EligibleSharingGroups:
        assert node_id == self.view.node_id
        assert snapshot.caller
        return EligibleSharingGroups(groups=(EligibleSharingGroup(
            group_id=" Exact ", label="Display label", description="Collaboration",
        ),))

    async def inspect(self, snapshot: CallerSnapshot, node_id: UUID) -> NodeGroupPolicyView:
        assert node_id == self.view.node_id
        assert snapshot.caller
        return self.view

    async def replace(
        self, snapshot: CallerSnapshot, node_id: UUID, command: ReplaceNodeGroupPolicy,
    ) -> NodeGroupPolicyView:
        assert node_id == self.view.node_id
        assert snapshot.caller
        self.commands.append(command)
        self.view = NodeGroupPolicyView(
            node_id=node_id, revision="after", groups=command.groups, blocked_group_ids=("protected",),
        )
        return self.view


def test_routes_use_sharing_port_and_return_its_authoritative_projection(sharing_http: FilesystemHttp) -> None:
    identifier = uuid4()
    service = RecordingSharing(identifier)

    def provide() -> FilesystemSharing:
        return service

    sharing_http.app.dependency_overrides[get_filesystem_sharing] = provide
    path = f"{BASE}/nodes/{identifier}/access"
    eligible = sharing_http.client.get(path + "/eligible-groups")
    assert eligible.status_code == 200
    assert eligible.json() == {"groups": [{
        "group_id": " Exact ", "label": "Display label", "description": "Collaboration",
    }]}
    assert "etag" not in eligible.headers
    assert eligible.headers["cache-control"] == "no-store"
    inspected = sharing_http.client.get(path)
    assert inspected.headers["etag"] == '\"before\"'
    saved = sharing_http.client.put(path, json={"groups": []}, headers={"If-Match": inspected.headers["etag"]})
    assert saved.status_code == 200
    assert saved.headers["etag"] == '\"after\"'
    assert saved.json() == service.view.model_dump(mode="json")
    assert service.commands == [ReplaceNodeGroupPolicy(expected_revision="before", groups=())]
