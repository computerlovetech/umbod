from typing import Final

from umbod.core.groups.stores.reads import read_registered_group_ids
from umbod.core.persistence import (
    AllFields,
    Database,
    DeleteQuery,
    Equals,
    Query,
    ReadSession,
    TransactionMode,
    Unordered,
    UpsertCommand,
)

from ..errors import SettingsStorageUnavailable
from ..ports import SettingsNotConfigured
from .errors import UnregisteredMappingGroups
from .models import ProviderGroupMappings
from .schema import (
    MAPPINGS_KEY,
    PROVIDER_GROUP_MAPPINGS_TABLE,
    ProviderGroupMappingsKey,
    ProviderGroupMappingsRow,
    StoredProviderGroupMappings,
)

_SINGLETON: Final[int] = 1


async def read_saved_provider_group_mappings(
    session: ReadSession,
) -> ProviderGroupMappings | SettingsNotConfigured:
    row = await session.find_one(
        PROVIDER_GROUP_MAPPINGS_TABLE,
        Query(Equals(MAPPINGS_KEY, _SINGLETON), AllFields(), Unordered()),
    )
    if row is None:
        return SettingsNotConfigured.UNSET
    return row.settings.root


class DatabaseProviderGroupMappingsStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def read(self) -> ProviderGroupMappings | SettingsNotConfigured:
        try:
            async with self._database.read_session() as session:
                return await read_saved_provider_group_mappings(session)
        except Exception:
            raise SettingsStorageUnavailable() from None

    async def replace(self, mappings: ProviderGroupMappings) -> None:
        try:
            async with self._database.session(
                mode=TransactionMode.SERIALIZED_WRITE
            ) as session:
                registered_groups = await read_registered_group_ids(session)
                unknown = tuple(
                    index
                    for index, mapping in enumerate(mappings)
                    if mapping.group_id not in registered_groups
                )
                if unknown:
                    raise UnregisteredMappingGroups(unknown)
                await session.upsert(
                    PROVIDER_GROUP_MAPPINGS_TABLE,
                    UpsertCommand(
                        key=ProviderGroupMappingsKey(singleton=_SINGLETON),
                        row=ProviderGroupMappingsRow(
                            singleton=_SINGLETON,
                            settings=StoredProviderGroupMappings(mappings),
                        ),
                    ),
                )
        except UnregisteredMappingGroups:
            raise
        except Exception:
            raise SettingsStorageUnavailable() from None

    async def reset(self) -> None:
        try:
            async with self._database.session(
                mode=TransactionMode.SERIALIZED_WRITE
            ) as session:
                await session.delete(
                    PROVIDER_GROUP_MAPPINGS_TABLE,
                    DeleteQuery(Equals(MAPPINGS_KEY, _SINGLETON)),
                )
        except Exception:
            raise SettingsStorageUnavailable() from None
