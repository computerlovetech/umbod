from pathlib import Path
from uuid import UUID, uuid4

import aiosqlite
import pytest

from tests.persistence_runtime import create_sqlite_runtime, prepared_sqlite_runtime
from umbod.core.groups import Group, GroupInstance, RegisterGroup, UpdateGroupMetadata
from umbod.core.groups.stores import registration
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.groups.stores.reads import DatabaseGroupInstanceLookup
from umbod.core.permissions.factories import create_group_permission_store
from umbod.core.persistence import Database
from umbod.core.system_settings.provider_group_mappings import (
    ProviderGroupMapping,
    create_provider_group_mappings_service,
)
from umbod.infrastructure.persistence.sqlite import schema_preparation


_LEGACY_IDS = ("", " ", "provider/team", "x" * 201)


async def _seed_legacy_groups(path: Path, *, with_metadata: bool) -> tuple[Group, ...]:
    groups = tuple(
        Group(group_id=group_id, label=group_id, description="", revision=1)
        for group_id in _LEGACY_IDS
    )
    async with aiosqlite.connect(path) as connection:
        if with_metadata:
            await connection.execute(
                "CREATE TABLE mcp_permission_groups (group_id TEXT PRIMARY KEY NOT NULL, "
                "label TEXT NOT NULL, description TEXT NOT NULL, revision INTEGER NOT NULL CHECK (revision > 0))"
            )
            groups = tuple(
                Group(
                    group_id=group_id,
                    label=" Label 雪 ",
                    description="Original\ntext",
                    revision=3,
                )
                for group_id in _LEGACY_IDS
            )
            await connection.executemany(
                "INSERT INTO mcp_permission_groups (group_id, label, description, revision) VALUES (?, ?, ?, ?)",
                [
                    (group.group_id, group.label, group.description, group.revision)
                    for group in groups
                ],
            )
        else:
            await connection.execute(
                "CREATE TABLE mcp_permission_groups (group_id TEXT PRIMARY KEY NOT NULL)"
            )
            await connection.executemany(
                "INSERT INTO mcp_permission_groups (group_id) VALUES (?)",
                [(group_id,) for group_id in _LEGACY_IDS],
            )
        await connection.commit()
    return groups


async def _read_instances(database: Database) -> tuple[GroupInstance, ...]:
    lookup = DatabaseGroupInstanceLookup(database)
    groups: list[GroupInstance] = []
    for group_id in _LEGACY_IDS:
        instance = await lookup.find_group_instance(group_id)
        assert instance is not None
        assert instance.group_id == group_id
        groups.append(instance)
    return tuple(groups)


@pytest.mark.asyncio
@pytest.mark.parametrize("with_metadata", [False, True])
async def test_legacy_sqlite_groups_are_backfilled_and_metadata_survives_reopen(
    tmp_path: Path,
    with_metadata: bool,
) -> None:
    path = tmp_path / "legacy.sqlite3"
    groups = await _seed_legacy_groups(path, with_metadata=with_metadata)
    mapping = ProviderGroupMapping(
        external_value="external-team", group_id="provider/team"
    )
    async with aiosqlite.connect(path) as connection:
        await connection.execute(
            "CREATE TABLE provider_group_mapping_settings (singleton INTEGER PRIMARY KEY NOT NULL, settings TEXT NOT NULL)"
        )
        await connection.execute(
            "INSERT INTO provider_group_mapping_settings (singleton, settings) VALUES (1, ?)",
            (f"[{mapping.model_dump_json()}]",),
        )
        await connection.commit()

    runtime = await prepared_sqlite_runtime(path)
    management = create_group_management(runtime.database)
    try:
        assert await management.list_groups() == groups
        instances = await _read_instances(runtime.database)
        assert len({instance.instance_id for instance in instances}) == len(groups)
        assert all(UUID(instance.instance_id).version == 4 for instance in instances)
        mappings = create_provider_group_mappings_service(runtime.database)
        saved_mappings = await mappings.get("administrator")
        assert saved_mappings.mappings == (mapping,)
        updated = await management.update_group_metadata(
            "provider/team",
            UpdateGroupMetadata(
                label="Team",
                description="Edited",
                expected_revision=3 if with_metadata else 1,
            ),
        )
        await runtime.readiness.ensure_ready()
        assert await _read_instances(runtime.database) == instances
    finally:
        await runtime.shutdown()

    reopened = await prepared_sqlite_runtime(path)
    try:
        management = create_group_management(reopened.database)
        await management.register_group(RegisterGroup(group_id="provider/team"))
        assert updated in await management.list_groups()
        assert await _read_instances(reopened.database) == instances
        mappings = create_provider_group_mappings_service(reopened.database)
        assert await mappings.get("administrator") == saved_mappings
        assert await mappings.replace("administrator", (mapping,)) == saved_mappings
        store = await create_group_permission_store(reopened.database)
        assert (
            tuple(group.group_id for group in await store.list_group_identifiers())
            == _LEGACY_IDS
        )
    finally:
        await reopened.shutdown()


@pytest.mark.asyncio
async def test_deleted_backfilled_instance_id_cannot_be_reallocated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "legacy.sqlite3"
    await _seed_legacy_groups(path, with_metadata=False)
    runtime = await prepared_sqlite_runtime(path)
    try:
        groups = create_group_management(runtime.database)
        lookup = DatabaseGroupInstanceLookup(runtime.database)
        original = await lookup.find_group_instance("provider/team")
        assert original is not None
        await groups.delete_group(original.group_id)

        replacement_id = uuid4()
        candidates = iter((UUID(hex=original.instance_id), replacement_id))
        monkeypatch.setattr(registration, "uuid4", candidates.__next__)
        await groups.register_group(RegisterGroup(group_id=original.group_id))

        current = await lookup.find_group_instance(original.group_id)
        assert current is not None and current.instance_id == replacement_id.hex
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_failed_instance_backfill_rolls_back_and_can_be_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "legacy.sqlite3"
    groups = await _seed_legacy_groups(path, with_metadata=False)
    repeated_id = UUID("aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa")
    runtime = create_sqlite_runtime(path)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(schema_preparation, "uuid4", lambda: repeated_id)
            with pytest.raises(
                aiosqlite.IntegrityError, match="mcp_permission_groups.instance_id"
            ):
                await runtime.readiness.ensure_ready()

        async with aiosqlite.connect(path) as connection:
            async with connection.execute(
                "SELECT * FROM mcp_permission_groups ORDER BY group_id"
            ) as cursor:
                assert await cursor.fetchall() == [
                    (group_id,) for group_id in _LEGACY_IDS
                ]

        await runtime.readiness.ensure_ready()
        assert await create_group_management(runtime.database).list_groups() == groups
        assert len(
            {
                instance.instance_id
                for instance in await _read_instances(runtime.database)
            }
        ) == len(groups)
    finally:
        await runtime.shutdown()
