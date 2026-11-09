from collections.abc import Iterator
from uuid import uuid4

import pytest

from umbod.core.filesystem.authorization import ResolvedIdentity
from umbod.core.filesystem.authorization.discovery import AuthorizationGrant, AuthorizationNode, EffectivePermissionEvaluator
from umbod.core.filesystem.models import NodeId, NodeKind, Ownership, Permission, Principal, PrincipalType, RootParent
from umbod.core.filesystem.namespace import ROOT_ID


def principal(identifier: str) -> Principal:
    return Principal(type=PrincipalType.USER, issuer="issuer", id=identifier)


@pytest.mark.parametrize("corruption", ["missing", "cycle", "file-parent", "detached", "root-kind"])
def test_malformed_ancestry_denies_direct_owner_and_matching_recursive_grants(corruption: str) -> None:
    parent_id, target_id = uuid4(), uuid4()
    root = AuthorizationNode(node_id=ROOT_ID, kind=NodeKind.DIRECTORY, parent_id=RootParent())
    parent = AuthorizationNode(node_id=parent_id, kind=NodeKind.DIRECTORY, parent_id=ROOT_ID)
    target = AuthorizationNode(node_id=target_id, kind=NodeKind.FILE, parent_id=parent_id)
    if corruption == "cycle":
        parent = parent.model_copy(update={"parent_id": target_id})
    elif corruption == "file-parent":
        parent = parent.model_copy(update={"kind": NodeKind.FILE})
    elif corruption == "detached":
        parent = parent.model_copy(update={"parent_id": RootParent()})
    elif corruption == "root-kind":
        root = root.model_copy(update={"kind": NodeKind.FILE})
    nodes = (root, target) if corruption == "missing" else (root, parent, target)
    evaluator = EffectivePermissionEvaluator(
        frozenset({principal("alice")}), nodes,
        (Ownership(node_id=target_id, owner=principal("alice")),),
        (AuthorizationGrant(node_id=ROOT_ID, principal=principal("alice"), permissions=frozenset(Permission), recursive=True),),
    )
    assert evaluator.permissions(target_id) == frozenset()
    assert evaluator.permissions(target_id) == frozenset()


def node_stream(target_ids: tuple[NodeId, ...]) -> Iterator[AuthorizationNode]:
    yield AuthorizationNode(node_id=ROOT_ID, kind=NodeKind.DIRECTORY, parent_id=RootParent())
    for target_id in target_ids:
        yield AuthorizationNode(node_id=target_id, kind=NodeKind.FILE, parent_id=ROOT_ID)


def test_indexed_evaluation_reuses_single_pass_facts_and_does_not_inherit_ownership() -> None:
    target_ids = tuple(uuid4() for _ in range(401))
    identity = ResolvedIdentity(user=principal("alice"), groups=frozenset())
    owners = (Ownership(node_id=target_id, owner=principal("bob")) for target_id in target_ids)
    grants = iter((AuthorizationGrant(
        node_id=ROOT_ID, principal=identity.user,
        permissions=frozenset({Permission.READ}), recursive=True,
    ),))
    evaluator = EffectivePermissionEvaluator(identity.principals, node_stream(target_ids), owners, grants)
    assert all(evaluator.permissions(target_id) == {Permission.READ} for target_id in reversed(target_ids))
    assert evaluator.permissions(ROOT_ID) == frozenset()
    owner_only = EffectivePermissionEvaluator(
        identity.principals, node_stream(target_ids),
        (Ownership(node_id=ROOT_ID, owner=identity.user), *(Ownership(node_id=target_id, owner=principal("bob")) for target_id in target_ids)), (),
    )
    assert owner_only.permissions(ROOT_ID) == frozenset(Permission)
    assert all(not owner_only.permissions(target_id) for target_id in target_ids)
