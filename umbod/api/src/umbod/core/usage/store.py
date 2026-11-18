from datetime import date, timedelta, timezone

from umbod.core.persistence import (
    AllFields, AllOf, Database, DatabaseSession, DeleteQuery, Equals,
    InsertCommand, LessThan, OneOf, Query, TransactionMode, Unordered, UpsertCommand,
)
from .models import (
    OutcomeCounts, OwnedUsageQuery, UsageBatch, UsageCounts, UsageDay, UsageKind,
    UsageOutcome, UsageRange, UsageRecord, UsageSummary, UsageTool, UsageTopTool, usage_tool_id,
)
from .otel import serialize_usage_otel, usage_occurred_at
from .schema import (
    EVENT_DAY, EVENT_TABLE, ROLLUP_DAY, ROLLUP_KIND, ROLLUP_OUTCOME, ROLLUP_OWNER,
    ROLLUP_TABLE, UsageEventRow, UsageRollupKey, UsageRollupRow,
    TOOL_DAILY_DAY, TOOL_DAILY_OWNER, TOOL_DAILY_ID, TOOL_DAILY_TABLE, UsageToolDailyKey, UsageToolDailyRow,
)


def _counts(values: dict[tuple[int, str, str], int], days: tuple[int, ...]) -> UsageCounts:
    return UsageCounts.model_validate({
        kind.value: OutcomeCounts.model_validate({
            outcome.value: sum(values.get((day, kind.value, outcome.value), 0) for day in days)
            for outcome in UsageOutcome
        })
        for kind in UsageKind
    })


async def _append_record(session: DatabaseSession, record: UsageRecord) -> None:
    day = usage_occurred_at(record).date().toordinal()
    inserted = await session.insert(
        EVENT_TABLE,
        InsertCommand(row=UsageEventRow(
            event_id=str(record.event_id), owner_id=record.owner_id,
            day=day, otel_json=serialize_usage_otel(record),
        )),
    )
    if not inserted:
        return
    key = UsageRollupKey(
        owner_id=record.owner_id, day=day, kind=record.kind.value, outcome=record.outcome.value,
    )
    existing = await session.find_one(
        ROLLUP_TABLE,
        Query(AllOf((
            Equals(ROLLUP_OWNER, key.owner_id), Equals(ROLLUP_DAY, key.day),
            Equals(ROLLUP_KIND, key.kind), Equals(ROLLUP_OUTCOME, key.outcome),
        )), AllFields(), Unordered()),
    )
    await session.upsert(
        ROLLUP_TABLE,
        UpsertCommand(
            key=key,
            row=UsageRollupRow(**key.model_dump(), count=1 if existing is None else existing.count + 1),
        ),
    )

    if record.kind == UsageKind.TOOL and isinstance(record.tool, UsageTool):
        await _increment_tool(session, record.tool, record.owner_id, day)


async def _increment_tool(session: DatabaseSession, tool: UsageTool, owner_id: str, day: int) -> None:
    key = UsageToolDailyKey(owner_id=owner_id, day=day, tool_id=usage_tool_id(tool.target))
    existing = await session.find_one(
        TOOL_DAILY_TABLE,
        Query(AllOf((
            Equals(TOOL_DAILY_OWNER, key.owner_id), Equals(TOOL_DAILY_DAY, key.day),
            Equals(TOOL_DAILY_ID, key.tool_id),
        )), AllFields(), Unordered()),
    )
    await session.upsert(TOOL_DAILY_TABLE, UpsertCommand(
        key=key, row=UsageToolDailyRow(
            **key.model_dump(), tool_name=tool.tool_name, connector_name=tool.connector_name,
            count=1 if existing is None else existing.count + 1,
        ),
    ))


def _top_tools(rows: tuple[UsageToolDailyRow, ...]) -> tuple[UsageTopTool, ...]:
    combined: dict[str, UsageTopTool] = {}
    for row in sorted(rows, key=lambda item: item.day):
        previous = combined.get(row.tool_id)
        combined[row.tool_id] = UsageTopTool(
            tool_id=row.tool_id, tool_name=row.tool_name, connector_name=row.connector_name,
            count=row.count + (previous.count if previous is not None else 0),
        )
    return tuple(sorted(combined.values(), key=lambda tool: (-tool.count, tool.tool_id))[:5])


class DatabaseUsageStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def append_usage(self, batch: UsageBatch) -> None:
        async with self._database.session(mode=TransactionMode.TRY_SERIALIZED_WRITE) as session:
            for record in batch.records:
                await _append_record(session, record)

    async def prune_usage(self, before: date) -> None:
        async with self._database.session(mode=TransactionMode.TRY_SERIALIZED_WRITE) as session:
            await session.delete(EVENT_TABLE, DeleteQuery(LessThan(EVENT_DAY, before.toordinal())))
            await session.delete(ROLLUP_TABLE, DeleteQuery(LessThan(ROLLUP_DAY, before.toordinal())))
            await session.delete(TOOL_DAILY_TABLE, DeleteQuery(LessThan(TOOL_DAILY_DAY, before.toordinal())))

    async def count_usage(self, query: OwnedUsageQuery) -> UsageSummary:
        as_of = query.as_of.astimezone(timezone.utc)
        end = as_of.date() + timedelta(days=1)
        start = end - timedelta(days=query.days)
        days = tuple(start.toordinal() + offset for offset in range(query.days))
        async with self._database.read_session() as session:
            rows = await session.find_many(
                ROLLUP_TABLE,
                Query(AllOf((
                    Equals(ROLLUP_OWNER, query.owner_id), OneOf(ROLLUP_DAY, days),
                )), AllFields(), Unordered()),
            )
            tool_rows = await session.find_many(
                TOOL_DAILY_TABLE,
                Query(AllOf((
                    Equals(TOOL_DAILY_OWNER, query.owner_id), OneOf(TOOL_DAILY_DAY, days),
                )), AllFields(), Unordered()),
            )
        values = {(row.day, row.kind, row.outcome): row.count for row in rows}
        return UsageSummary(
            range=UsageRange(start=start, end=end, timezone="UTC"),
            as_of=as_of,
            totals=_counts(values, days),
            top_tools=_top_tools(tuple(tool_rows)),
            daily=tuple(
                UsageDay(date=date.fromordinal(day), counts=_counts(values, (day,)))
                for day in days
            ),
        )
