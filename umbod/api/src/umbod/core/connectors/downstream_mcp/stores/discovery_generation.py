from typing import cast

from pydantic import BaseModel, ConfigDict

from umbod.core.persistence import AllFields, DatabaseSession, Equals, Field, IntegerCodec, KeyCodec, Query, RowCodec, Table, TableIdentity, TextCodec, Unordered, UpsertCommand


class DiscoveryGenerationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    revision: int


class DiscoveryGenerationKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str


_IDENTITY = TableIdentity("downstream_mcp_discovery_generations")
_CONNECTOR_ID = Field[DiscoveryGenerationRecord, str](_IDENTITY, "connector_id", TextCodec())
_REVISION = Field[DiscoveryGenerationRecord, int](_IDENTITY, "revision", IntegerCodec())
DISCOVERY_GENERATION_TABLE = Table(
    _IDENTITY,
    RowCodec(DiscoveryGenerationRecord, cast(tuple[Field[DiscoveryGenerationRecord, object], ...], (_CONNECTOR_ID, _REVISION))),
    KeyCodec(DiscoveryGenerationKey, cast(tuple[Field[DiscoveryGenerationRecord, object], ...], (_CONNECTOR_ID,))),
)


async def discovery_generation(session: DatabaseSession, connector_id: str) -> int:
    row = await session.find_one(DISCOVERY_GENERATION_TABLE, Query(
        filter=Equals(_CONNECTOR_ID, connector_id), projection=AllFields(), ordering=Unordered(),
    ))
    return 0 if row is None else row.revision


async def advance_discovery_generation(session: DatabaseSession, connector_id: str) -> None:
    revision = await discovery_generation(session, connector_id)
    await session.upsert(DISCOVERY_GENERATION_TABLE, UpsertCommand(
        key=DiscoveryGenerationKey(connector_id=connector_id),
        row=DiscoveryGenerationRecord(connector_id=connector_id, revision=revision + 1),
    ))
