from datetime import datetime, timezone
from unittest.mock import create_autospec
from uuid import UUID, uuid4

import pytest

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType
from umbod.core.filesystem.authorization import FilesystemIdentityResolver
from umbod.core.filesystem.sharing import (
    EligibleSharingGroup, EligibleSharingGroups,
    FilesystemSharing, InvalidSharingPolicy, SharingPolicyUnavailable,
    NodePolicyView, ReplaceNodePolicy, SharingScope, SharingRecipientType,
    GroupSharingTarget, SharingGrantSummary,
)
from umbod.core.persistence import Database, TransactionMode
from umbod.core.groups import RegisterGroupMetadata
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.groups.stores.registration import register_group_in_session
from umbod.core.identity_directory.models import IdentityObservation
from umbod.core.identity_directory.store import DatabaseIdentityDirectory
from umbod.core.identity_directory.user_models import ScopedUserSearch
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
    root = sharing_http.client.get(BASE + "/browse").json()["node"]
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
    initial = client.get(path, params={"recipient_type": "group"})
    assert initial.status_code == 200, initial.text
    assert set(initial.json()) == {"node_id", "revision", "grants", "blocked_recipients"}
    assert initial.json()["grants"] == []
    assert initial.headers["etag"] == '"' + initial.json()["revision"] + '"'
    grants = [{"recipient": {"type": "group", "group_id": "team"}, "permissions": ["discover", "share"]}]
    saved = client.put(path, params={"recipient_type": "group"}, json={"grants": grants}, headers={"If-Match": initial.headers["etag"]})
    assert saved.status_code == 200, saved.text
    assert saved.headers["etag"] != initial.headers["etag"]
    assert saved.json() == client.get(path, params={"recipient_type": "group"}).json()
    assert set(saved.json()["grants"][0]["permissions"]) == {"discover", "share"}
    assert client.get(f"{BASE}/nodes/{private_node['id']}").json() == private_node
    bob = {"Authorization": "Bearer bob"}
    assert client.get(path, headers=bob).status_code == 200
    revoked = client.put(path, params={"recipient_type": "group"}, json={"grants": []}, headers={**bob, "If-Match": saved.headers["etag"]})
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["grants"] == []
    assert client.get(path, headers=bob).status_code == 403
    stale = client.put(path, params={"recipient_type": "group"}, json={"grants": grants}, headers={"If-Match": saved.headers["etag"]})
    assert stale.status_code == 412
    for response in (initial, saved, revoked, stale):
        assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("permissions", [{Permission.DISCOVER}, {Permission.SHARE}, set()])
@pytest.mark.parametrize("method", ["GET", "PUT"])
@pytest.mark.parametrize("recipient_type", ["group", "user"])
def test_missing_discover_or_share_denies_before_stale_revision_and_unknown_recipient(
    sharing_http: FilesystemHttp, private_node: dict[str, object], permissions: set[Permission], method: str,
    recipient_type: str,
) -> None:
    if permissions:
        grant_recipient(sharing_http, private_node, permissions)
    headers = {"Authorization": "Bearer bob", "If-Match": OPAQUE}
    body = {"grants": [{"recipient": {
        "type": recipient_type, f"{recipient_type}_id": "secret-unregistered",
    }, "permissions": ["read"]}]}
    denied = sharing_http.client.request(method, access_path(private_node), json=body, headers=headers, params={"recipient_type": recipient_type})
    missing = sharing_http.client.request(method, f"{BASE}/nodes/{uuid4()}/access", json=body, headers=headers, params={"recipient_type": recipient_type})
    assert denied.status_code == missing.status_code == 403
    assert denied.json() == missing.json()
    assert "secret" not in denied.text


@pytest.mark.parametrize("header", ["", "*", 'W/"abc"', "abc", '""', '"1"', '"abc", "def"'])
def test_sharing_preconditions_are_not_content_revisions(
    sharing_http: FilesystemHttp, private_node: dict[str, object], header: str,
) -> None:
    response = sharing_http.client.put(access_path(private_node), params={"recipient_type": "group"}, json={"grants": []}, headers={"If-Match": header})
    assert response.status_code == 422


def test_sharing_requires_precondition_and_rejects_multiple_headers(
    sharing_http: FilesystemHttp, private_node: dict[str, object],
) -> None:
    path = access_path(private_node)
    assert sharing_http.client.put(path, params={"recipient_type": "group"}, json={"grants": []}).status_code == 428
    response = sharing_http.client.put(path, params={"recipient_type": "group"}, json={"grants": []}, headers=[("If-Match", OPAQUE), ("If-Match", OPAQUE)])
    assert response.status_code == 422


@pytest.mark.parametrize("body", [
    {"groups": []}, {"grants": [], "issuer": "evil"}, {"grants": [], "users": []},
    {"grants": [], "recursive": True}, {"grants": [], "expected_revision": "abc"},
    {"grants": [{"recipient": {"type": "group", "group_id": "team"}, "permissions": ["read"], "issuer": "evil"}]},
    {"grants": [{"recipient": {"type": "group", "group_id": "team"}, "permissions": ["read"], "recursive": True}]},
    {"grants": [{"recipient": {"type": "group", "group_id": "team"}, "permissions": []}]},
    {"grants": [{"recipient": {"type": "group", "group_id": " "}, "permissions": ["read"]}]},
    {"grants": [{"recipient": {"type": "group", "group_id": "team"}, "permissions": ["read"]}] * 2},
    *[{"grants": [{"recipient": {"type": "group", "group_id": "team", field: "evil"}, "permissions": ["read"]}]}
      for field in ("issuer", "recursive", "label", "user_id")],
    {"grants": [{"recipient": {"type": "user", "user_id": "observed"}, "permissions": ["read"]}]},
])
def test_canonical_request_rejects_obsolete_or_extra_authority_without_writes(
    sharing_http: FilesystemHttp, private_node: dict[str, object], body: dict[str, object],
) -> None:
    path = access_path(private_node)
    before = sharing_http.client.get(path)
    response = sharing_http.client.put(path, params={"recipient_type": "group"}, json=body, headers={"If-Match": before.headers["etag"]})
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert sharing_http.client.get(path).json() == before.json()


def test_group_ids_are_exact_registered_recipients_without_automatic_creation(
    sharing_http: FilesystemHttp, private_node: dict[str, object],
) -> None:
    register_recipient(sharing_http, " Exact ")
    path = access_path(private_node)
    initial = sharing_http.client.get(path)
    rejected = sharing_http.client.put(path, params={"recipient_type": "group"}, json={"grants": [{"recipient": {"type": "group", "group_id": "Exact"}, "permissions": ["read"]}]}, headers={"If-Match": initial.headers["etag"]})
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "filesystem_sharing_invalid"
    assert "Exact" not in rejected.text
    assert sharing_http.client.get(path).json() == initial.json()
    accepted = sharing_http.client.put(path, params={"recipient_type": "group"}, json={"grants": [{"recipient": {"type": "group", "group_id": " Exact "}, "permissions": ["read"]}]}, headers={"If-Match": initial.headers["etag"]})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["grants"][0]["recipient"]["group_id"] == " Exact "


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


def test_group_replacement_preserves_foreign_user_and_recursive_grants(
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
    initial = sharing_http.client.get(path, params={"recipient_type": "group"})
    assert initial.json()["grants"] == []
    assert initial.json()["blocked_recipients"] == [{"type": "group", "group_id": "team"}]
    collision = sharing_http.client.put(path, params={"recipient_type": "group"}, json={"grants": [{"recipient": {"type": "group", "group_id": "team"}, "permissions": ["read"]}]}, headers={"If-Match": initial.headers["etag"]})
    assert collision.status_code == 422
    revoked = sharing_http.client.put(path, params={"recipient_type": "group"}, json={"grants": []}, headers={"If-Match": initial.headers["etag"]})
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
        self.view = NodePolicyView(node_id=node_id, revision="before", grants=(), blocked_recipients=())
        self.commands: list[ReplaceNodePolicy] = []
        self.scopes: list[SharingScope] = []

    async def eligible_groups(self, snapshot: CallerSnapshot, node_id: UUID) -> EligibleSharingGroups:
        assert node_id == self.view.node_id
        assert snapshot.caller
        return EligibleSharingGroups(groups=(EligibleSharingGroup(
            group_id=" Exact ", label="Display label", description="Collaboration",
        ),))

    async def inspect(self, snapshot: CallerSnapshot, node_id: UUID, scope: SharingScope) -> NodePolicyView:
        self.scopes.append(scope)
        assert node_id == self.view.node_id
        assert snapshot.caller
        return self.view

    async def replace(
        self, snapshot: CallerSnapshot, node_id: UUID, command: ReplaceNodePolicy,
    ) -> NodePolicyView:
        assert node_id == self.view.node_id
        assert snapshot.caller
        self.commands.append(command)
        self.view = NodePolicyView(
            node_id=node_id, revision="after", grants=tuple(
                SharingGrantSummary.model_validate({
                    "recipient": {**grant.recipient.model_dump(), "label": "Authoritative label"},
                    "permissions": grant.permissions,
                }) for grant in command.grants
            ),
            blocked_recipients=(GroupSharingTarget(type="group", group_id="protected"),),
        )
        return self.view


@pytest.mark.parametrize("recipient_type", ["group", "user"])
def test_routes_use_sharing_port_and_return_its_authoritative_projection(
    sharing_http: FilesystemHttp, recipient_type: SharingRecipientType,
) -> None:
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
    recipient = (
        {"type": "group", "group_id": " Exact "}
        if recipient_type == "group" else {"type": "user", "user_id": "observed"}
    )
    saved = sharing_http.client.put(path, params={"recipient_type": recipient_type}, json={"grants": [
        {"recipient": recipient, "permissions": ["read"]},
    ]}, headers={"If-Match": inspected.headers["etag"]})
    assert saved.status_code == 200
    assert saved.headers["etag"] == '\"after\"'
    assert saved.json() == service.view.model_dump(mode="json")
    assert service.scopes == [SharingScope(recipient_types=frozenset(("group", "user")))]
    assert len(service.commands) == 1
    assert service.commands[0].model_dump(mode="json") == {
        "recipient_type": recipient_type, "expected_revision": "before",
        "grants": [{"recipient": recipient, "permissions": ["read"]}],
    }


def observe_user(http: FilesystemHttp, issuer: str, subject: str, label: str) -> str:
    async def observe() -> str:
        directory = DatabaseIdentityDirectory(http.factories.persistence_runtime.database)
        await directory.observe(IdentityObservation(
            issuer=issuer, subject=subject, claim="filesystem_groups", groups=(), name=label,
            email="private@example.test", email_verification="verified",
            observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ))
        page = await directory.search_user_names(ScopedUserSearch(
            issuer=issuer, query=label, limit=50, excluded_subjects=frozenset(),
        ))
        return page.users[0].user_id

    return http.client.portal.call(observe)


@pytest.fixture
def observed_user(sharing_http: FilesystemHttp) -> str:
    return observe_user(sharing_http, "issuer", "bob", "Bob Reader")


@pytest.fixture
def mixed_policy(
    sharing_http: FilesystemHttp, private_node: dict[str, object], observed_user: str,
) -> dict[str, object]:
    path = access_path(private_node)
    for recipient in (
        {"type": "group", "group_id": "team"},
        {"type": "user", "user_id": observed_user},
    ):
        revision = sharing_http.client.get(path).headers["etag"]
        response = sharing_http.client.put(
            path, params={"recipient_type": recipient["type"]},
            json={"grants": [{"recipient": recipient, "permissions": ["discover", "read"]}]},
            headers={"If-Match": revision},
        )
        assert response.status_code == 200, response.text
    return private_node


@pytest.mark.parametrize("recipient_type", ["group", "user", "both"])
def test_get_returns_canonical_labeled_recipients_with_one_global_revision(
    sharing_http: FilesystemHttp, mixed_policy: dict[str, object],
    observed_user: str, recipient_type: str,
) -> None:
    path = access_path(mixed_policy)
    complete = sharing_http.client.get(path)
    params = {} if recipient_type == "both" else {"recipient_type": recipient_type}
    response = sharing_http.client.get(path, params=params)
    expected = [
        {"recipient": {"type": "group", "group_id": "team", "label": "team"}, "permissions": ["discover", "read"]},
        {"recipient": {"type": "user", "user_id": observed_user, "label": "Bob Reader"}, "permissions": ["discover", "read"]},
    ]
    assert response.status_code == 200
    assert response.json() == {
        "node_id": mixed_policy["id"], "revision": complete.json()["revision"],
        "grants": [grant for grant in expected if recipient_type == "both" or grant["recipient"]["type"] == recipient_type],
        "blocked_recipients": [],
    }
    assert response.headers["etag"] == complete.headers["etag"]
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("recipient_type", ["group", "user"])
def test_replacement_only_removes_selected_type_and_returns_selected_view(
    sharing_http: FilesystemHttp, mixed_policy: dict[str, object], recipient_type: str,
) -> None:
    path = access_path(mixed_policy)
    before = sharing_http.client.get(path)
    response = sharing_http.client.put(
        path, params={"recipient_type": recipient_type}, json={"grants": []},
        headers={"If-Match": before.headers["etag"]},
    )
    assert response.status_code == 200
    assert response.json()["grants"] == []
    assert response.headers["etag"] != before.headers["etag"]
    complete = sharing_http.client.get(path)
    assert complete.json()["grants"] == [
        grant for grant in before.json()["grants"] if grant["recipient"]["type"] != recipient_type
    ]
    assert complete.headers["etag"] == response.headers["etag"]
    assert sharing_http.client.get(path, params={"recipient_type": recipient_type}).json() == response.json()


def test_user_change_invalidates_group_etag_without_modifying_group_grants(
    sharing_http: FilesystemHttp, mixed_policy: dict[str, object],
) -> None:
    path = access_path(mixed_policy)
    groups = sharing_http.client.get(path, params={"recipient_type": "group"})
    users = sharing_http.client.put(
        path, params={"recipient_type": "user"}, json={"grants": []},
        headers={"If-Match": groups.headers["etag"]},
    )
    assert users.status_code == 200
    stale = sharing_http.client.put(
        path, params={"recipient_type": "group"}, json={"grants": []},
        headers={"If-Match": groups.headers["etag"]},
    )
    assert stale.status_code == 412
    current = sharing_http.client.get(path, params={"recipient_type": "group"})
    assert current.json()["grants"] == groups.json()["grants"]
    assert current.headers["etag"] == users.headers["etag"]
    assert stale.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("method", ["GET", "PUT"])
@pytest.mark.parametrize("query", [
    "recipient_type=", "recipient_type=invalid", "recipient_type=GROUP",
    "recipient_type=group&recipient_type=user", "recipient_type=user&recipient_type=user",
    "recipient_type=group&recipient_type=group", "recipient_type=%20group%20",
])
def test_invalid_recipient_query_is_rejected_without_mutation(
    sharing_http: FilesystemHttp, mixed_policy: dict[str, object], method: str, query: str,
) -> None:
    path = access_path(mixed_policy)
    before = sharing_http.client.get(path)
    response = sharing_http.client.request(
        method, path + "?" + query, json={"grants": []},
        headers={"If-Match": before.headers["etag"]},
    )
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    after = sharing_http.client.get(path)
    assert after.json() == before.json()
    assert after.headers["etag"] == before.headers["etag"]


def test_put_requires_explicit_recipient_type_without_mutation(
    sharing_http: FilesystemHttp, mixed_policy: dict[str, object],
) -> None:
    path = access_path(mixed_policy)
    before = sharing_http.client.get(path)
    response = sharing_http.client.put(
        path, json={"grants": []}, headers={"If-Match": before.headers["etag"]},
    )
    assert response.status_code == 422
    assert sharing_http.client.get(path).json() == before.json()


@pytest.mark.parametrize("recipient_type", ["group", "user"])
def test_valid_recipient_scope_still_requires_if_match(
    sharing_http: FilesystemHttp, mixed_policy: dict[str, object], recipient_type: str,
) -> None:
    path = access_path(mixed_policy)
    before = sharing_http.client.get(path)
    response = sharing_http.client.put(path, params={"recipient_type": recipient_type}, json={"grants": []})
    assert response.status_code == 428
    assert response.json()["detail"]["code"] == "filesystem_precondition_required"
    assert sharing_http.client.get(path).json() == before.json()


@pytest.mark.parametrize("invalid_kind", ["duplicate", "mismatch", "label"])
def test_user_replacement_rejects_duplicate_mismatched_or_response_recipients(
    sharing_http: FilesystemHttp, mixed_policy: dict[str, object], observed_user: str, invalid_kind: str,
) -> None:
    path = access_path(mixed_policy)
    before = sharing_http.client.get(path)
    recipient = {"type": "user", "user_id": observed_user}
    if invalid_kind == "mismatch":
        recipient = {"type": "group", "group_id": "team"}
    if invalid_kind == "label":
        recipient["label"] = "Bob Reader"
    grants = [{"recipient": recipient, "permissions": ["read"]}] * (2 if invalid_kind == "duplicate" else 1)
    response = sharing_http.client.put(
        path, params={"recipient_type": "user"}, json={"grants": grants},
        headers={"If-Match": before.headers["etag"]},
    )
    assert response.status_code == 422
    assert sharing_http.client.get(path).json() == before.json()


@pytest.mark.parametrize("invalid_identity", ["subject", "foreign_issuer", "unknown"])
def test_user_targets_resolve_only_observed_ids_in_the_exact_configured_issuer(
    sharing_http: FilesystemHttp, private_node: dict[str, object], observed_user: str, invalid_identity: str,
) -> None:
    identifier = {
        "subject": "bob", "unknown": "never-observed",
        "foreign_issuer": observe_user(sharing_http, " issuer ", "bob", "Foreign Bob"),
    }[invalid_identity]
    assert observed_user != "bob"
    path = access_path(private_node)
    before = sharing_http.client.get(path)
    response = sharing_http.client.put(
        path, params={"recipient_type": "user"},
        json={"grants": [{"recipient": {"type": "user", "user_id": identifier}, "permissions": ["read"]}]},
        headers={"If-Match": before.headers["etag"]},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "filesystem_sharing_invalid"
    assert "Foreign Bob" not in response.text
    assert sharing_http.client.get(path).json() == before.json()


def test_observed_user_id_binds_to_subject_for_direct_authorization_and_revocation(
    sharing_http: FilesystemHttp, private_node: dict[str, object], observed_user: str,
) -> None:
    path = access_path(private_node)
    before = sharing_http.client.get(path)
    saved = sharing_http.client.put(
        path, params={"recipient_type": "user"},
        json={"grants": [{"recipient": {"type": "user", "user_id": observed_user}, "permissions": ["discover", "share"]}]},
        headers={"If-Match": before.headers["etag"]},
    )
    assert saved.status_code == 200, saved.text
    driver = create_access_control_driver(database=sharing_http.factories.persistence_runtime.database)
    stored = sharing_http.client.portal.call(driver.list_grants, UUID(str(private_node["id"])))
    assert stored == [AccessGrant(
        node_id=UUID(str(private_node["id"])),
        principal=Principal(type=PrincipalType.USER, issuer="issuer", id="bob"),
        permissions={Permission.DISCOVER, Permission.SHARE}, recursive=False,
    )]
    bob = {"Authorization": "Bearer bob"}
    assert sharing_http.client.get(path, headers=bob).status_code == 200
    revoked = sharing_http.client.put(
        path, params={"recipient_type": "user"}, json={"grants": []},
        headers={**bob, "If-Match": saved.headers["etag"]},
    )
    assert revoked.status_code == 200
    assert sharing_http.client.get(path, headers=bob).status_code == 403


@pytest.mark.parametrize("query,types", [
    ("", frozenset(("group", "user"))),
    ("?recipient_type=group", frozenset(("group",))),
    ("?recipient_type=user", frozenset(("user",))),
])
def test_inspection_passes_explicit_sharing_scope_to_port(
    sharing_http: FilesystemHttp, query: str, types: frozenset[SharingRecipientType],
) -> None:
    identifier = uuid4()
    service = RecordingSharing(identifier)

    def provide() -> FilesystemSharing:
        return service

    sharing_http.app.dependency_overrides[get_filesystem_sharing] = provide
    response = sharing_http.client.get(f"{BASE}/nodes/{identifier}/access" + query)
    assert response.status_code == 200
    assert service.scopes == [SharingScope(recipient_types=types)]
    assert service.commands == []


def test_user_replacement_preserves_recursive_foreign_and_unobserved_grants(
    sharing_http: FilesystemHttp, private_node: dict[str, object], observed_user: str,
) -> None:
    driver = create_access_control_driver(database=sharing_http.factories.persistence_runtime.database)
    identifier = UUID(str(private_node["id"]))
    protected = [
        AccessGrant(
            node_id=identifier, principal=Principal(type=PrincipalType.USER, issuer=issuer, id=subject),
            permissions={Permission.READ}, recursive=recursive,
        )
        for issuer, subject, recursive in (
            ("issuer", "bob", True), ("foreign", "bob", False),
            ("issuer", "unobserved-subject", False),
        )
    ]
    for grant in protected:
        sharing_http.client.portal.call(driver.add_grant, grant)
    path = access_path(private_node)
    before = sharing_http.client.get(path)
    users = sharing_http.client.get(path, params={"recipient_type": "user"})
    assert users.json()["grants"] == []
    assert users.json()["blocked_recipients"] == [{"type": "user", "user_id": observed_user}]
    groups = sharing_http.client.get(path, params={"recipient_type": "group"})
    assert groups.json()["blocked_recipients"] == []
    assert users.headers["etag"] == groups.headers["etag"] == before.headers["etag"]
    collision = sharing_http.client.put(
        path, params={"recipient_type": "user"},
        json={"grants": [{"recipient": {"type": "user", "user_id": observed_user}, "permissions": ["read"]}]},
        headers={"If-Match": before.headers["etag"]},
    )
    assert collision.status_code == 422
    unchanged = sharing_http.client.put(
        path, params={"recipient_type": "user"}, json={"grants": []},
        headers={"If-Match": before.headers["etag"]},
    )
    assert unchanged.status_code == 200
    assert unchanged.json() == users.json()
    assert unchanged.headers["etag"] == before.headers["etag"]
    stored = sharing_http.client.portal.call(driver.list_grants, identifier)
    assert len(stored) == len(protected)
    assert all(grant in stored for grant in protected)
