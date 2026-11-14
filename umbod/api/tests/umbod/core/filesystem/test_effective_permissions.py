from uuid import uuid4

import pytest
from pydantic import ValidationError

from umbod.core.filesystem.authorization.discovery import AuthorizationNode, EffectivePermissionEvaluator
from umbod.core.filesystem.models import AccessGrant, NodeId, NodeKind, Ownership, Permission, Principal, PrincipalType, RootParent
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.core.filesystem.namespaces import NamespacePolicy


def principal(identifier: str) -> Principal:
    return Principal(type=PrincipalType.USER, issuer="issuer", id=identifier)


def policy(root_id: NodeId) -> NamespacePolicy:
    return NamespacePolicy(id=uuid4(), root_node_id=root_id, name="Personal", kind="personal", issuer="issuer", revision=1, owners=frozenset({principal("alice")}), grants=())


@pytest.mark.parametrize("corruption", ["missing", "cycle", "file-parent", "detached", "root-kind"])
def test_managed_namespace_never_bypasses_complete_ancestry_validation(corruption: str) -> None:
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
    owner = Ownership(node_id=target_id, owner=principal("alice"))
    grants = (AccessGrant(node_id=target_id, principal=principal("alice"), permissions=set(Permission), recursive=True), AccessGrant(node_id=ROOT_ID, principal=principal("alice"), permissions=set(Permission), recursive=True))
    evaluator = EffectivePermissionEvaluator(frozenset({principal("alice")}), nodes, (owner,), grants, (policy(parent_id),))
    assert not evaluator.permissions(target_id)
    assert not evaluator.permissions(target_id)


def test_single_pass_facts_and_nearest_namespace_boundary() -> None:
    outer_id, inner_id = uuid4(), uuid4()
    targets = tuple(uuid4() for _ in range(401))
    nodes = (
        AuthorizationNode(node_id=ROOT_ID, kind=NodeKind.DIRECTORY, parent_id=RootParent()),
        AuthorizationNode(node_id=outer_id, kind=NodeKind.DIRECTORY, parent_id=ROOT_ID),
        AuthorizationNode(node_id=inner_id, kind=NodeKind.DIRECTORY, parent_id=outer_id),
        *(AuthorizationNode(node_id=value, kind=NodeKind.FILE, parent_id=inner_id) for value in targets),
    )
    outer = policy(outer_id)
    inner = policy(inner_id).model_copy(update={"owners": frozenset({principal("bob")})})
    evaluator = EffectivePermissionEvaluator(frozenset({principal("alice")}), iter(nodes), (), (), iter((outer, inner)))
    assert evaluator.permissions(outer_id) == frozenset(Permission) - {Permission.SHARE}
    assert not evaluator.permissions(ROOT_ID)
    assert all(not evaluator.permissions(value) for value in reversed(targets))
    assert not EffectivePermissionEvaluator(frozenset({principal("alice")}), iter(nodes), (), (), ()).permissions(outer_id)


def test_duplicate_authorization_facts_are_rejected() -> None:
    root = AuthorizationNode(node_id=ROOT_ID, kind=NodeKind.DIRECTORY, parent_id=RootParent())
    with pytest.raises(ValueError, match="Duplicate authorization node"):
        EffectivePermissionEvaluator(frozenset(), (root, root), (), (), ())
    namespace = policy(uuid4())
    with pytest.raises(ValueError, match="Duplicate namespace roots"):
        EffectivePermissionEvaluator(frozenset(), (root,), (), (), (namespace, namespace))
    with pytest.raises(ValidationError):
        policy(ROOT_ID)


@pytest.mark.parametrize("recursive", [False, True])
def test_ownership_is_direct_and_only_recursive_grants_reach_descendants(recursive: bool) -> None:
    namespace_id, parent_id, leaf_id = uuid4(), uuid4(), uuid4()
    namespace = policy(namespace_id).model_copy(update={"owners": frozenset({principal("namespace-owner")})})
    nodes = (
        AuthorizationNode(node_id=ROOT_ID, kind=NodeKind.DIRECTORY, parent_id=RootParent()),
        AuthorizationNode(node_id=namespace_id, kind=NodeKind.DIRECTORY, parent_id=ROOT_ID),
        AuthorizationNode(node_id=parent_id, kind=NodeKind.DIRECTORY, parent_id=namespace_id),
        AuthorizationNode(node_id=leaf_id, kind=NodeKind.FILE, parent_id=parent_id),
    )
    owners = (Ownership(node_id=parent_id, owner=principal("alice")),)
    grants = (AccessGrant(node_id=parent_id, principal=principal("alice"), permissions={Permission.DISCOVER}, recursive=recursive),)
    evaluator = EffectivePermissionEvaluator(frozenset({principal("alice")}), iter(nodes), iter(owners), iter(grants), (namespace,))
    assert evaluator.permissions(parent_id) == frozenset(Permission)
    assert evaluator.permissions(leaf_id) == ({Permission.DISCOVER} if recursive else frozenset())
    assert evaluator.permissions(leaf_id) == ({Permission.DISCOVER} if recursive else frozenset())
    assert not evaluator.permissions(namespace_id)
