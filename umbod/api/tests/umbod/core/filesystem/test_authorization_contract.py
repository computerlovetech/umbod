from unittest.mock import Mock, create_autospec
from uuid import uuid4

import pytest
from pydantic import ValidationError

from umbod.core.filesystem import (
    AccessControlDriver,
    AccessGrant,
    MissingNode,
    NamespaceDriver,
    Node,
    Ownership,
    OwnershipNotFound,
    Permission,
    Principal,
    PrincipalType,
    StorageFailure,
)
from umbod.core.filesystem.authorization import (
    AuthorizationDecision,
    AuthorizationService,
    FilesystemAuthorization,
    FilesystemIdentityResolver,
    ResolvedIdentity,
    UnresolvedIdentity,
)
from tests.support.filesystem.authorization import caller, principal


@pytest.mark.parametrize("missing", ["user", "groups"])
def test_resolved_identity_requires_explicit_user_and_groups(missing: str) -> None:
    values: dict[str, object] = {"user": principal("alice", PrincipalType.USER, "provider"), "groups": []}
    del values[missing]
    with pytest.raises(ValidationError):
        ResolvedIdentity.model_validate(values)


@pytest.mark.parametrize("user,groups", [
    (principal("team", PrincipalType.GROUP, "provider"), []),
    (principal("alice", PrincipalType.USER, "provider"), [principal("another-user", PrincipalType.USER, "provider")]),
])
def test_resolved_identity_rejects_wrong_principal_types(
    user: Principal, groups: list[Principal],
) -> None:
    with pytest.raises(ValidationError):
        ResolvedIdentity(user=user, groups=groups)


def test_resolved_identity_freezes_and_detaches_supplied_groups() -> None:
    team = principal("team", PrincipalType.GROUP, "provider")
    groups = {team}
    identity = ResolvedIdentity(user=principal("alice", PrincipalType.USER, "provider"), groups=groups)
    groups.clear()
    assert identity.groups == frozenset({team})
    assert identity.principals == frozenset({principal("alice", PrincipalType.USER, "provider"), team})
    with pytest.raises(ValidationError):
        identity.groups = frozenset()
    with pytest.raises(ValidationError):
        identity.user.id = "changed"
    with pytest.raises(AttributeError):
        identity.groups.clear()


def test_authorization_decisions_and_unresolved_state_are_immutable() -> None:
    decision = AuthorizationDecision(node_id=uuid4(), permission=Permission.READ, allowed=False)
    with pytest.raises(ValidationError):
        decision.allowed = True
    unresolved = UnresolvedIdentity()
    with pytest.raises(ValidationError):
        unresolved.user = principal("alice", PrincipalType.USER, "provider")


@pytest.fixture
def resolver() -> Mock:
    resolver = create_autospec(FilesystemIdentityResolver, instance=True, spec_set=True)
    resolver.resolve.return_value = ResolvedIdentity(user=principal("alice", PrincipalType.USER, "provider"), groups=[])
    return resolver


@pytest.fixture
def namespace() -> Mock:
    return create_autospec(NamespaceDriver, instance=True, spec_set=True)


@pytest.fixture
def policies() -> Mock:
    policies = create_autospec(AccessControlDriver, instance=True, spec_set=True)
    policies.get_owner.return_value = Ownership(node_id=uuid4(), owner=principal("other", PrincipalType.USER, "provider"))
    policies.list_grants.return_value = []
    return policies


@pytest.fixture
def authorization(resolver: Mock, namespace: Mock, policies: Mock) -> FilesystemAuthorization:
    return AuthorizationService(resolver=resolver, namespace=namespace, access_control=policies)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["decide", "require"])
@pytest.mark.parametrize("source", ["resolver", "node", "owner", "grants"])
@pytest.mark.parametrize("failure", [StorageFailure("unavailable"), RuntimeError("unexpected")])
async def test_resolver_and_storage_failures_propagate_without_becoming_denials(
    authorization: FilesystemAuthorization, resolver: Mock, namespace: Mock,
    policies: Mock, source: str, failure: Exception, operation: str,
) -> None:
    methods = {
        "resolver": resolver.resolve, "node": namespace.get_node,
        "owner": policies.get_owner, "grants": policies.list_grants,
    }
    methods[source].side_effect = failure
    with pytest.raises(type(failure)) as caught:
        await getattr(authorization, operation)(caller("alice"), uuid4(), Permission.READ)
    assert caught.value is failure


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [MissingNode(), OwnershipNotFound()])
async def test_resolver_missing_errors_are_not_misreported_as_storage_absence(
    authorization: FilesystemAuthorization, resolver: Mock, failure: Exception,
) -> None:
    resolver.resolve.side_effect = failure
    with pytest.raises(type(failure)):
        await authorization.decide(caller("alice"), uuid4(), Permission.READ)


@pytest.mark.asyncio
async def test_unresolved_identity_denies_without_using_storage(
    authorization: FilesystemAuthorization, resolver: Mock, namespace: Mock, policies: Mock,
) -> None:
    resolver.resolve.return_value = UnresolvedIdentity()
    assert not (await authorization.decide(caller("alice"), uuid4(), Permission.READ)).allowed
    assert namespace.mock_calls == []
    assert policies.mock_calls == []


@pytest.mark.asyncio
async def test_evaluation_only_reads_target_node_owner_and_direct_grants(
    authorization: FilesystemAuthorization, namespace: Mock, policies: Mock,
) -> None:
    node_id = uuid4()
    namespace.get_node.return_value = create_autospec(Node, instance=True)
    policies.list_grants.return_value = [AccessGrant(
        node_id=node_id, principal=principal("alice", PrincipalType.USER, "provider"), permissions={Permission.READ}, recursive=True,
    )]
    assert (await authorization.decide(caller("alice"), node_id, Permission.READ)).allowed
    assert namespace.mock_calls == [("get_node", (node_id,), {})]
    assert policies.mock_calls == [
        ("get_owner", (node_id,), {}), ("list_grants", (node_id,), {}),
    ]


@pytest.mark.asyncio
async def test_grant_for_another_node_cannot_authorize_target_even_if_returned_by_driver(
    authorization: FilesystemAuthorization, policies: Mock,
) -> None:
    policies.list_grants.return_value = [AccessGrant(
        node_id=uuid4(), principal=principal("alice", PrincipalType.USER, "provider"), permissions={Permission.READ}, recursive=True,
    )]
    assert not (await authorization.decide(caller("alice"), uuid4(), Permission.READ)).allowed
