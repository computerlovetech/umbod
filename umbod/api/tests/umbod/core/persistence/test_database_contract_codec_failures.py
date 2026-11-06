from dataclasses import dataclass, replace
from typing import ClassVar, Literal, cast

import pytest

from umbod.core.persistence import (
    AllFields,
    ColumnCodec,
    ColumnType,
    Database,
    Field,
    InsertCommand,
    NoFilter,
    OrderBy,
    Query,
    Table,
    TextCodec,
    TransactionMode,
    UpsertCommand,
)
from tests.umbod.core.persistence.contract_support import SampleKey, SampleRow, row, table


@dataclass(frozen=True)
class RejectingTextCodec(ColumnCodec[str]):
    column_type: ClassVar[ColumnType] = ColumnType.TEXT
    error_type: type[Exception]

    def encode(self, value: str) -> object:
        if value == "reject":
            raise self.error_type("rejected text")
        return TextCodec().encode(value)

    def decode(self, value: object) -> str:
        return TextCodec().decode(value)


def _rejecting_table(
    error_type: type[Exception],
) -> tuple[Table[SampleRow, SampleKey], Field[SampleRow, str]]:
    contract_table, owner, record, payload = table("codec_rejections")
    rejecting_payload = replace(payload, codec=RejectingTextCodec(error_type))
    fields = cast(tuple[Field[SampleRow, object], ...], (owner, record, rejecting_payload))
    return (
        replace(contract_table, row_codec=replace(contract_table.row_codec, fields=fields)),
        record,
    )


@pytest.mark.parametrize("mode", [TransactionMode.READ_WRITE, TransactionMode.SERIALIZED_WRITE])
@pytest.mark.parametrize("error_type", [AttributeError, TypeError, ValueError])
@pytest.mark.asyncio
async def test_caught_insert_codec_error_preserves_writes_and_session_remains_usable(
    database: Database, mode: TransactionMode, error_type: type[Exception],
) -> None:
    contract_table, record = _rejecting_table(error_type)
    retained = row("retained", "committed seed")
    before = row("before", "earlier valid write")
    after = row("after", "later valid write")
    await database.ensure_schema((contract_table,))
    async with database.session(mode=mode) as session:
        await session.insert(contract_table, InsertCommand(row=retained))

    async with database.session(mode=mode) as session:
        await session.insert(contract_table, InsertCommand(row=before))
        with pytest.raises(
            TypeError, match=r"Invalid value for codec_rejections\.payload: rejected text",
        ) as caught:
            await session.insert(contract_table, InsertCommand(row=row("rejected", "reject")))
        assert type(caught.value.__cause__) is error_type
        await session.insert(contract_table, InsertCommand(row=after))

    async with database.read_session() as session:
        observed = await session.find_many(
            contract_table, Query(NoFilter(), AllFields(), OrderBy((record,))),
        )
    assert tuple(observed) == (after, before, retained)


@pytest.mark.parametrize("mode", [TransactionMode.READ_WRITE, TransactionMode.SERIALIZED_WRITE])
@pytest.mark.parametrize("target_exists", [False, True])
@pytest.mark.asyncio
async def test_caught_upsert_codec_error_preserves_target_and_allows_recovery_write(
    database: Database, mode: TransactionMode, target_exists: bool,
) -> None:
    contract_table, record = _rejecting_table(ValueError)
    retained = row("retained", "unrelated committed seed")
    original_target = row("target", "original target")
    recovery = row("recovery", "valid recovery write")
    rejected = row("target", "reject")
    await database.ensure_schema((contract_table,))
    async with database.session(mode=mode) as session:
        await session.insert(contract_table, InsertCommand(row=retained))
        if target_exists:
            await session.insert(contract_table, InsertCommand(row=original_target))

    async with database.session(mode=mode) as session:
        with pytest.raises(
            TypeError, match=r"Invalid value for codec_rejections\.payload: rejected text",
        ):
            await session.upsert(
                contract_table,
                UpsertCommand(
                    key=SampleKey(owner_id=rejected.owner_id, record_id=rejected.record_id),
                    row=rejected,
                ),
            )
        await session.upsert(
            contract_table,
            UpsertCommand(
                key=SampleKey(owner_id=recovery.owner_id, record_id=recovery.record_id),
                row=recovery,
            ),
        )

    async with database.read_session() as session:
        observed = await session.find_many(
            contract_table, Query(NoFilter(), AllFields(), OrderBy((record,))),
        )
    expected = (recovery, retained, original_target) if target_exists else (recovery, retained)
    assert tuple(observed) == expected


@pytest.mark.parametrize("mode", [TransactionMode.READ_WRITE, TransactionMode.SERIALIZED_WRITE])
@pytest.mark.parametrize("operation", ["insert", "upsert"])
@pytest.mark.asyncio
async def test_escaping_codec_error_rolls_back_prior_writes_and_new_session_recovers(
    database: Database, mode: TransactionMode, operation: Literal["insert", "upsert"],
) -> None:
    contract_table, record = _rejecting_table(ValueError)
    original = row("retained", "original committed seed")
    updated = row("retained", "pending update")
    pending = row("pending", "pending insert")
    rejected = row("rejected", "reject")
    recovered = row("recovered", "new session recovery")
    await database.ensure_schema((contract_table,))
    async with database.session(mode=mode) as session:
        await session.insert(contract_table, InsertCommand(row=original))

    with pytest.raises(
        TypeError, match=r"Invalid value for codec_rejections\.payload: rejected text",
    ):
        async with database.session(mode=mode) as session:
            await session.upsert(
                contract_table,
                UpsertCommand(
                    key=SampleKey(owner_id=updated.owner_id, record_id=updated.record_id),
                    row=updated,
                ),
            )
            await session.insert(contract_table, InsertCommand(row=pending))
            if operation == "insert":
                await session.insert(contract_table, InsertCommand(row=rejected))
            else:
                await session.upsert(
                    contract_table,
                    UpsertCommand(
                        key=SampleKey(owner_id=rejected.owner_id, record_id=rejected.record_id),
                        row=rejected,
                    ),
                )

    async with database.read_session() as session:
        observed = await session.find_many(
            contract_table, Query(NoFilter(), AllFields(), OrderBy((record,))),
        )
    assert tuple(observed) == (original,)

    async with database.session(mode=mode) as session:
        await session.insert(contract_table, InsertCommand(row=recovered))
    async with database.read_session() as session:
        observed_after_recovery = await session.find_many(
            contract_table, Query(NoFilter(), AllFields(), OrderBy((record,))),
        )
    assert tuple(observed_after_recovery) == (recovered, original)
