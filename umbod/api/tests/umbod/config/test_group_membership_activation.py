from collections.abc import AsyncIterator
from typing import cast

import pytest
import pytest_asyncio

from tests.persistence_runtime import prepared_inmemory_runtime
from umbod.config import AppConfig
from umbod.config.app import McpConfig, OidcConfig
from umbod.config.group_membership import ConfiguredGroupMembershipSource
from umbod.core.callers.membership import UNAVAILABLE_GROUP_MEMBERSHIP, GroupMembershipResolver
from umbod.core.groups import RegisterGroup
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.persistence import (
    Database,
    Field,
    IntegerCodec,
    JsonValueCodec,
    KeyCodec,
    RowCodec,
    Table,
    TransactionMode,
    UpsertCommand,
)
from umbod.core.system_settings import SettingsStorageUnavailable
from umbod.core.system_settings.provider_group_mappings import (
    ProviderGroupMapping,
    create_provider_group_mappings_service,
)
from umbod.core.system_settings.provider_group_mappings.schema import (
    MAPPINGS_IDENTITY,
    ProviderGroupMappingsKey,
)

_ADMINISTRATOR = "administrator"
_ISSUER = "https://identity.example.test/"
_RULE = ProviderGroupMapping(external_value="staff", group_id="team")
_OVERRIDE = ProviderGroupMapping(external_value="staff", group_id="another-team")


class _RawRow(ProviderGroupMappingsKey):
    settings: object


_KEY = Field[_RawRow, int](MAPPINGS_IDENTITY, "singleton", IntegerCodec())
_VALUE = Field[_RawRow, object](MAPPINGS_IDENTITY, "settings", JsonValueCodec())
_RAW_TABLE = Table(
    MAPPINGS_IDENTITY,
    RowCodec(_RawRow, (cast(Field[_RawRow, object], _KEY), _VALUE)),
    KeyCodec(ProviderGroupMappingsKey, (cast(Field[_RawRow, object], _KEY),)),
)


async def _write_raw_row(database: Database, payload: object) -> None:
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await session.upsert(
            _RAW_TABLE,
            UpsertCommand(
                key=ProviderGroupMappingsKey(singleton=1),
                row=_RawRow(singleton=1, settings=payload),
            ),
        )


@pytest_asyncio.fixture
async def database() -> AsyncIterator[Database]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield runtime.database
    finally:
        await runtime.shutdown()


def _oidc_config(claim: str = "groups") -> AppConfig:
    return AppConfig(
        oidc=OidcConfig(issuer_url=_ISSUER),
        mcp=McpConfig(auth_mode="oidc", permission_group_claim=claim),
    )


def _resolved_groups(resolver: GroupMembershipResolver) -> frozenset[str]:
    return frozenset(
        resolver.resolve_verified(
            {"iss": _ISSUER, "groups": ["staff", "unmatched", "team"], "roles": ["team"]},
        ).group_ids
    )


@pytest.mark.asyncio
async def test_captures_only_saved_rules_until_reset(database: Database) -> None:
    groups = create_group_management(database)
    await groups.register_group(RegisterGroup(group_id="team"))
    await groups.register_group(RegisterGroup(group_id="another-team"))
    config = _oidc_config()
    source = ConfiguredGroupMembershipSource(config, database)
    admin = create_provider_group_mappings_service(database)
    before_save = await source.capture()
    assert _resolved_groups(before_save) == set()

    await admin.replace(_ADMINISTRATOR, (_OVERRIDE,))
    assert (await admin.get(_ADMINISTRATOR)).mappings == (_OVERRIDE,)
    assert _resolved_groups(await source.capture()) == {"another-team"}
    assert _resolved_groups(before_save) == set()
    assert await source.target_group_ids() == frozenset({"another-team"})

    await admin.reset(_ADMINISTRATOR)
    assert _resolved_groups(await source.capture()) == set()
    assert await source.target_group_ids() == frozenset()


@pytest.mark.asyncio
async def test_deleted_target_does_not_grant_membership(database: Database) -> None:
    groups = create_group_management(database)
    await groups.register_group(RegisterGroup(group_id="team"))
    config = _oidc_config()
    source = ConfiguredGroupMembershipSource(config, database)
    await create_provider_group_mappings_service(database).replace(_ADMINISTRATOR, (_RULE,))
    await groups.delete_group("team")

    assert _resolved_groups(await source.capture()) == set()


@pytest.mark.asyncio
async def test_deleted_target_does_not_remove_other_targets_for_same_value(database: Database) -> None:
    groups = create_group_management(database)
    await groups.register_group(RegisterGroup(group_id="team"))
    await groups.register_group(RegisterGroup(group_id="other"))
    config = _oidc_config()
    source = ConfiguredGroupMembershipSource(config, database)
    other_rule = ProviderGroupMapping(external_value="staff", group_id="other")
    await create_provider_group_mappings_service(database).replace(_ADMINISTRATOR, (_RULE, other_rule))
    await groups.delete_group("team")

    assert _resolved_groups(await source.capture()) == {"other"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        None,
        {"mappings": [{**_RULE.model_dump(), "issuer": _ISSUER, "claim": "groups"}], "published": False},
        [{**_RULE.model_dump(), "group_id": None}],
        [{**_RULE.model_dump(), "claim": "groups"}],
        [_RULE.model_dump(), _RULE.model_dump()],
    ],
)
async def test_unreadable_saved_rules_fail_closed_until_admin_reset(
    database: Database, payload: object,
) -> None:
    await _write_raw_row(database, payload)
    config = _oidc_config()
    source = ConfiguredGroupMembershipSource(config, database)
    admin = create_provider_group_mappings_service(database)

    assert await source.capture() is UNAVAILABLE_GROUP_MEMBERSHIP
    with pytest.raises(SettingsStorageUnavailable):
        await source.target_group_ids()
    with pytest.raises(SettingsStorageUnavailable):
        await admin.get(_ADMINISTRATOR)

    await admin.reset(_ADMINISTRATOR)
    assert _resolved_groups(await source.capture()) == set()
