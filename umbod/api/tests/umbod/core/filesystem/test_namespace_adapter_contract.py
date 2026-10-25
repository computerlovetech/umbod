import asyncio
from uuid import uuid4

import pytest

from umbod.core.filesystem import (
    ContentRef,
    EmptyContent,
    InvalidName,
    MissingNode,
    NameCollision,
    Node,
    NodeKind,
    NodeMetadata,
    RevisionConflict,
    RootParent,
    UnspecifiedContentType,
    WrongNodeKind,
)

from tests.support.filesystem.adapters import AdapterFactory, AdapterPair


def metadata() -> NodeMetadata:
    return NodeMetadata(content_type=UnspecifiedContentType(), attributes={"team": "research"})


@pytest.mark.asyncio
async def test_concurrent_callers_discover_one_root(adapter_factory: AdapterFactory) -> None:
    roots = await asyncio.gather(*(adapter_factory().namespace.get_root() for _ in range(8)))

    assert len({root.id for root in roots}) == 1
    assert all(root.name == "" and root.kind == NodeKind.DIRECTORY for root in roots)
    assert all(isinstance(root.parent_id, RootParent) for root in roots)
    assert all(isinstance(root.content, EmptyContent) for root in roots)


@pytest.mark.asyncio
async def test_names_are_exact_and_listings_are_sorted(adapters: AdapterPair) -> None:
    namespace = adapters.namespace
    root = await namespace.get_root()
    names = ("report", "Report", "é", "e\u0301", " leading ", " ")
    for name in names:
        await namespace.create_node(root.id, name, NodeKind.FILE, metadata())

    assert [node.name for node in await namespace.list_children(root.id)] == sorted(names)
    assert await namespace.get_root() == root


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["", ".", "..", "a/b", "a\\b", "a\x00b", "\ud800"])
async def test_invalid_names_leave_namespace_unchanged(adapters: AdapterPair, name: str) -> None:
    root = await adapters.namespace.get_root()

    with pytest.raises(InvalidName):
        await adapters.namespace.create_node(root.id, name, NodeKind.FILE, metadata())

    assert tuple(await adapters.namespace.list_children(root.id)) == ()
    assert await adapters.namespace.get_root() == root


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [NodeKind.FILE, NodeKind.DIRECTORY])
async def test_duplicate_names_are_rejected_across_node_kinds(
    adapters: AdapterPair, kind: NodeKind,
) -> None:
    root = await adapters.namespace.get_root()
    original = await adapters.namespace.create_node(root.id, "occupied", NodeKind.FILE, metadata())

    with pytest.raises(NameCollision):
        await adapters.namespace.create_node(root.id, "occupied", kind, metadata())

    assert tuple(await adapters.namespace.list_children(root.id)) == (original,)


@pytest.mark.asyncio
async def test_concurrent_duplicate_creation_has_one_winner(adapter_factory: AdapterFactory) -> None:
    first = adapter_factory().namespace
    second = adapter_factory().namespace
    root = await first.get_root()

    results = await asyncio.gather(
        first.create_node(root.id, "same", NodeKind.FILE, metadata()),
        second.create_node(root.id, "same", NodeKind.FILE, metadata()),
        return_exceptions=True,
    )

    assert sum(isinstance(result, Node) for result in results) == 1
    assert sum(isinstance(result, NameCollision) for result in results) == 1
    assert len(await first.list_children(root.id)) == 1


@pytest.mark.asyncio
async def test_independent_callers_preserve_each_others_creations(adapter_factory: AdapterFactory) -> None:
    root = await adapter_factory().namespace.get_root()
    names = tuple(f"file-{index}" for index in range(10))

    await asyncio.gather(*(
        adapter_factory().namespace.create_node(root.id, name, NodeKind.FILE, metadata())
        for name in names
    ))

    children = await adapter_factory().namespace.list_children(root.id)
    assert {node.name for node in children} == set(names)


@pytest.mark.asyncio
async def test_missing_nodes_are_distinct_domain_failures(adapters: AdapterPair) -> None:
    with pytest.raises(MissingNode):
        await adapters.namespace.get_node(uuid4())
    with pytest.raises(MissingNode):
        await adapters.namespace.list_children(uuid4())
    with pytest.raises(MissingNode):
        await adapters.namespace.create_node(uuid4(), "child", NodeKind.FILE, metadata())


@pytest.mark.asyncio
async def test_files_cannot_be_parents_or_have_children_listed(adapters: AdapterPair) -> None:
    root = await adapters.namespace.get_root()
    file = await adapters.namespace.create_node(root.id, "file", NodeKind.FILE, metadata())

    with pytest.raises(WrongNodeKind):
        await adapters.namespace.create_node(file.id, "child", NodeKind.FILE, metadata())
    with pytest.raises(WrongNodeKind):
        await adapters.namespace.list_children(file.id)

    assert await adapters.namespace.get_node(file.id) == file


@pytest.mark.asyncio
async def test_metadata_cannot_mutate_namespace_without_revision_checks(adapters: AdapterPair) -> None:
    root = await adapters.namespace.get_root()
    supplied = metadata()
    created = await adapters.namespace.create_node(root.id, "file", NodeKind.FILE, supplied)
    supplied.attributes["team"] = "changed-input"
    created.metadata.attributes["team"] = "changed-result"
    retrieved = await adapters.namespace.get_node(created.id)

    assert retrieved.metadata.attributes == {"team": "research"}
    retrieved.metadata.attributes["team"] = "changed-read"
    listed = (await adapters.namespace.list_children(root.id))[0]
    assert listed.metadata.attributes == {"team": "research"}


@pytest.mark.asyncio
async def test_content_publication_checks_revisions_and_preserves_parent(adapters: AdapterPair) -> None:
    root = await adapters.namespace.get_root()
    file = await adapters.namespace.create_node(root.id, "file", NodeKind.FILE, metadata())
    reference = ContentRef(key=uuid4().hex, size=3)
    published = await adapters.namespace.update_node(
        file.id, content=reference, expected_revision=file.revision,
    )

    assert published.content == reference
    assert published.revision == file.revision + 1
    assert published.created_at == file.created_at
    assert published.updated_at >= file.updated_at
    assert await adapters.namespace.get_root() == root
    with pytest.raises(RevisionConflict):
        await adapters.namespace.update_node(
            file.id, content=ContentRef(key=uuid4().hex, size=4), expected_revision=file.revision,
        )
    assert await adapters.namespace.get_node(file.id) == published


@pytest.mark.asyncio
async def test_directories_cannot_receive_content_references(adapters: AdapterPair) -> None:
    root = await adapters.namespace.get_root()

    with pytest.raises(WrongNodeKind):
        await adapters.namespace.update_node(
            root.id, content=ContentRef(key=uuid4().hex, size=1), expected_revision=root.revision,
        )

    assert await adapters.namespace.get_root() == root
