from datetime import datetime, timezone
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from pydantic import ConfigDict, model_validator
from typing import Self

from umbod.proxies import Model
from umbod.core.groups.stores.schema import GROUP_ID, GROUP_TABLE
from umbod.core.persistence import AllFields, Database, DatabaseSession, DeleteQuery, Equals, Field, KeyCodec, NoFilter, PersistenceDecodingError, PydanticJsonCodec, Query, ReadSession, RowCodec, Table, TableIdentity, TextCodec, TransactionMode, Unordered, UpsertCommand

from ..errors import PolicyConflict, PolicyRevisionConflict, PolicyUnavailable
from ..authorization import PermissionDenied
from ..errors import MissingNode, OwnershipNotFound, NameCollision
from ..namespaces.errors import NamespaceActiveUploads, NamespaceNotEmpty, NamespaceNotFound, NamespaceValidationError
from ..homes.models import HomeBinding
from ..models import Node, NodeId, NodeKind, NodeMetadata, NodeUpdate, Ownership, Permission, Principal, PrincipalType, RootParent, SYSTEM_ROOT_OWNER, UnspecifiedContentType
from ..namespace import ROOT_ID, updated_details
from ..namespaces.models import CreateSharedNamespace, DeleteSharedNamespace, NamespaceDetails, NamespaceGrant, NamespacePolicy, SaveSharedNamespace, SaveSharedNamespaceDescription, SharedNamespaceView
from .access_control import SessionAccessControl
from .discovery_events import append_discovery_changed
from .homes import HOME_TABLE, SessionHomes
from .namespace import SessionNamespace, node_record
from .schema import NODE_ID, NODE_KEY_PROJECTION, NODE_PARENT, NODE_TABLE, NodeKey
from .session import storage_session
from .uploads import SessionUploads


class NamespaceKey(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")
    namespace_id: str


class NamespaceRecord(NamespaceKey):
    root_node_id: str
    payload: NamespacePolicy

    @model_validator(mode="after")
    def validate_indexes(self) -> Self:
        if self.namespace_id != str(self.payload.id) or self.root_node_id != str(self.payload.root_node_id):
            raise ValueError("Namespace index mismatch")
        return self


NAMESPACE_IDENTITY = TableIdentity("filesystem_namespaces")
NAMESPACE_ID = Field[NamespaceRecord, str](NAMESPACE_IDENTITY, "namespace_id", TextCodec())
NAMESPACE_ROOT = Field[NamespaceRecord, str](NAMESPACE_IDENTITY, "root_node_id", TextCodec())
NAMESPACE_PAYLOAD = Field[NamespaceRecord, NamespacePolicy](NAMESPACE_IDENTITY, "payload", PydanticJsonCodec(NamespacePolicy))
NAMESPACE_TABLE = Table(
    NAMESPACE_IDENTITY,
    RowCodec(NamespaceRecord, cast(tuple[Field[NamespaceRecord, object], ...], (NAMESPACE_ID, NAMESPACE_ROOT, NAMESPACE_PAYLOAD))),
    KeyCodec(NamespaceKey, cast(tuple[Field[NamespaceRecord, object], ...], (NAMESPACE_ID,))),
)


async def namespace_policies(session: ReadSession) -> list[NamespacePolicy]:
    records = await session.find_many(NAMESPACE_TABLE, Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()))
    policies = [record.payload for record in records]
    roots = {policy.root_node_id for policy in policies}
    if len(roots) != len(policies):
        raise ValueError("Duplicate namespace roots")
    return policies


async def persist_policy(session: DatabaseSession, policy: NamespacePolicy) -> None:
    key = NamespaceKey(namespace_id=str(policy.id))
    await session.upsert(NAMESPACE_TABLE, UpsertCommand(key=key, row=NamespaceRecord(**key.model_dump(), root_node_id=str(policy.root_node_id), payload=policy)))
    await append_discovery_changed(session)


def personal_policy(binding: HomeBinding) -> NamespacePolicy:
    namespace_id = uuid5(NAMESPACE_URL, binding.model_dump_json())
    return NamespacePolicy(id=namespace_id, root_node_id=binding.node_id, name="My files", kind="personal", issuer=binding.user.issuer, revision=1, owners=frozenset({binding.user}), grants=())


async def adopt_personal(session: DatabaseSession, binding: HomeBinding) -> NamespacePolicy:
    records = await session.find_many(NAMESPACE_TABLE, Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()))
    policies = [record.payload for record in records]
    for policy in policies:
        if policy.kind == "personal" and binding.user in policy.owners:
            if policy.root_node_id != binding.node_id:
                raise PermissionDenied()
            return policy
        if policy.root_node_id == binding.node_id:
            raise PermissionDenied()
    namespace = SessionNamespace(session)
    try:
        node = await namespace.get_node(binding.node_id)
        ownership = await SessionAccessControl(session).get_owner(binding.node_id)
    except (MissingNode, OwnershipNotFound):
        raise PermissionDenied() from None
    if node.id == ROOT_ID or node.kind != NodeKind.DIRECTORY or ownership.owner != binding.user:
        raise PermissionDenied()
    policy = personal_policy(binding)
    await persist_policy(session, policy)
    return policy


async def adopt_existing_homes(database: Database) -> None:
    async with storage_session(database, TransactionMode.SERIALIZED_WRITE) as session:
        homes = await session.find_many(HOME_TABLE, Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()))
        namespace = SessionNamespace(session)
        access = SessionAccessControl(session)
        for home in homes:
            try:
                node = await namespace.get_node(home.payload.node_id)
                owner = await access.get_owner(home.payload.node_id)
            except (MissingNode, OwnershipNotFound):
                continue
            if node.id != ROOT_ID and node.kind == NodeKind.DIRECTORY and owner.owner == home.payload.user:
                await adopt_personal(session, home.payload)


def require_shared_policy(policies: list[NamespacePolicy], namespace_id: UUID, issuer: str, expected_revision: int) -> NamespacePolicy:
    for policy in policies:
        if policy.id == namespace_id and policy.kind == "shared":
            if policy.issuer != issuer:
                raise PolicyUnavailable()
            if policy.revision != expected_revision:
                raise PolicyRevisionConflict()
            return policy
    raise NamespaceNotFound()


async def verified_shared_root(namespace: SessionNamespace, policy: NamespacePolicy, policies: list[NamespacePolicy]) -> Node:
    try:
        root = await namespace.get_node(policy.root_node_id)
        if root.id == ROOT_ID or root.kind != NodeKind.DIRECTORY or root.name != policy.name or isinstance(root.parent_id, RootParent):
            raise PolicyUnavailable()
        structural_root = await namespace.get_root()
        if root.parent_id != ROOT_ID:
            parent = await namespace.get_node(root.parent_id)
            if parent.kind != NodeKind.DIRECTORY or parent.parent_id != ROOT_ID or any(entry.root_node_id == parent.id for entry in policies):
                raise PolicyUnavailable()
        if structural_root.kind != NodeKind.DIRECTORY or not isinstance(structural_root.parent_id, RootParent) or structural_root.name != "":
            raise PolicyUnavailable()
    except (MissingNode, PersistenceDecodingError):
        raise PolicyUnavailable() from None
    return root


class DatabaseNamespaceRegistry:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def list(self) -> list[NamespaceDetails]:
        async with self._database.read_session() as session:
            policies = await namespace_policies(session)
            namespace = SessionNamespace(session)
            details: list[NamespaceDetails] = []
            for policy in policies:
                root = await namespace.get_node(policy.root_node_id)
                details.append(NamespaceDetails(policy=policy, description=root.metadata.attributes.get("description", ""), root_revision=root.revision))
            return details

    async def provision_personal(self, user: Principal) -> NamespacePolicy:
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            namespace = SessionNamespace(session)
            access = SessionAccessControl(session)
            await namespace.initialize_root()
            homes = SessionHomes(session)
            binding = await homes.get(user)
            if binding is None:
                node = await namespace.create_node(ROOT_ID, f"Home-{uuid4()}", NodeKind.DIRECTORY, NodeMetadata(content_type=UnspecifiedContentType(), attributes={}))
                await access.set_owner(Ownership(node_id=node.id, owner=user))
                binding = HomeBinding(user=user, node_id=node.id)
                await homes.save(binding)
            try:
                node = await namespace.get_node(binding.node_id)
            except MissingNode:
                raise PermissionDenied() from None
            if binding.user != user or node.kind != NodeKind.DIRECTORY or node.id == ROOT_ID:
                raise PermissionDenied()
            return await adopt_personal(session, binding)

    async def _validate_groups(self, session: DatabaseSession, command: CreateSharedNamespace | SaveSharedNamespace | SaveSharedNamespaceDescription) -> None:
        for group in command.groups:
            record = await session.find_one(GROUP_TABLE, Query(filter=Equals(GROUP_ID, group.group_id), projection=AllFields(), ordering=Unordered()))
            if record is None:
                raise NamespaceValidationError("Unknown permission group")

    def _policy(self, view: SharedNamespaceView, issuer: str) -> NamespacePolicy:
        return NamespacePolicy(
            id=view.id, root_node_id=view.root_node_id, name=view.name, kind="shared", issuer=issuer, revision=view.revision, owners=frozenset(),
            grants=tuple(NamespaceGrant(node_id=view.root_node_id, principal=Principal(type=PrincipalType.GROUP, issuer=issuer, id=group.group_id), permissions={Permission.DISCOVER, Permission.READ, *({Permission.WRITE, Permission.DELETE} if group.access == "read_write" else set())}, recursive=True) for group in view.groups),
        )

    async def _create_container(self, session: DatabaseSession) -> NodeId:
        try:
            container = await SessionNamespace(session).create_node(ROOT_ID, str(uuid4()), NodeKind.DIRECTORY, NodeMetadata(content_type=UnspecifiedContentType(), attributes={}))
        except NameCollision:
            raise PolicyConflict() from None
        await SessionAccessControl(session).set_owner(Ownership(node_id=container.id, owner=SYSTEM_ROOT_OWNER))
        return container.id

    async def create(self, command: CreateSharedNamespace, issuer: str) -> SharedNamespaceView:
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            policies = await namespace_policies(session)
            if any(policy.kind == "shared" and policy.name == command.name for policy in policies):
                raise PolicyConflict()
            await self._validate_groups(session, command)
            namespace = SessionNamespace(session)
            await namespace.initialize_root()
            container_id = await self._create_container(session)
            node = await namespace.create_node(container_id, command.name, NodeKind.DIRECTORY, NodeMetadata(content_type=UnspecifiedContentType(), attributes={"description": command.description} if command.description else {}))
            await SessionAccessControl(session).set_owner(Ownership(node_id=node.id, owner=SYSTEM_ROOT_OWNER))
            view = SharedNamespaceView(**command.model_dump(), id=uuid4(), root_node_id=node.id, revision=1, root_revision=node.revision)
            await persist_policy(session, self._policy(view, issuer))
            return view

    async def save(self, namespace_id: UUID, command: SaveSharedNamespace | SaveSharedNamespaceDescription, issuer: str) -> SharedNamespaceView:
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            policies = await namespace_policies(session)
            try:
                policy = require_shared_policy(policies, namespace_id, issuer, command.expected_revision)
            except NamespaceNotFound:
                raise PolicyConflict() from None
            if any(other.kind == "shared" and other.id != namespace_id and other.name == command.name for other in policies):
                raise PolicyConflict()
            await self._validate_groups(session, command)
            node = await SessionNamespace(session).get_node(policy.root_node_id)
            if isinstance(command, SaveSharedNamespaceDescription) and node.revision != command.expected_root_revision:
                raise PolicyRevisionConflict()
            parent_id = node.parent_id
            if node.name != command.name:
                if parent_id == ROOT_ID:
                    parent_id = await self._create_container(session)
                else:
                    if not isinstance(parent_id, UUID):
                        raise PolicyConflict()
                    parent = await SessionNamespace(session).get_node(parent_id)
                    if parent.parent_id != ROOT_ID or parent.kind != NodeKind.DIRECTORY or any(other.root_node_id == parent_id for other in policies):
                        raise PolicyConflict()
                siblings = await SessionNamespace(session).list_children(parent_id)
                if any(sibling.id != node.id and sibling.name == command.name for sibling in siblings):
                    raise PolicyConflict()
            attributes = dict(node.metadata.attributes)
            if isinstance(command, SaveSharedNamespaceDescription):
                attributes.pop("description", None)
                if command.description:
                    attributes["description"] = command.description
            metadata = NodeMetadata(content_type=node.metadata.content_type, attributes=attributes)
            if node.name != command.name or metadata != node.metadata:
                node = updated_details(node, NodeUpdate(name=command.name, parent_id=parent_id, metadata=metadata), node.revision)
                await session.upsert(NODE_TABLE, UpsertCommand(key=NodeKey(node_id=str(node.id)), row=node_record(node)))
            view = SharedNamespaceView(name=command.name, groups=command.groups, description=node.metadata.attributes.get("description", ""), root_revision=node.revision, id=namespace_id, root_node_id=policy.root_node_id, revision=policy.revision + 1)
            await persist_policy(session, self._policy(view, issuer))
            return view

    async def delete(self, namespace_id: UUID, command: DeleteSharedNamespace, issuer: str) -> None:
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            policies = await namespace_policies(session)
            policy = require_shared_policy(policies, namespace_id, issuer, command.expected_revision)
            root = await verified_shared_root(SessionNamespace(session), policy, policies)
            if root.revision != command.expected_root_revision:
                raise PolicyRevisionConflict()
            child = await session.find_one(
                NODE_TABLE, Query(Equals(NODE_PARENT, str(root.id)), NODE_KEY_PROJECTION, Unordered()),
            )
            if child is not None:
                raise NamespaceNotEmpty()
            if await SessionUploads(session).has_active_destination(root.id, datetime.now(timezone.utc)):
                raise NamespaceActiveUploads()
            await session.delete(NAMESPACE_TABLE, DeleteQuery(Equals(NAMESPACE_ID, str(policy.id))))
            await session.delete(NODE_TABLE, DeleteQuery(Equals(NODE_ID, str(root.id))))
            await SessionAccessControl(session).clear_node(root.id)
