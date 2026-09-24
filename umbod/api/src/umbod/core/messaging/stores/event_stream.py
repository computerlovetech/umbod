from collections.abc import Sequence

from pydantic import TypeAdapter

from umbod.core.messaging.stores.schema import (
    EVENT_SEQUENCE,
    EVENT_TABLE,
    EVENT_TYPE,
    MessagingEventRecord,
)
from umbod.core.persistence import (
    AllFields,
    AllOf,
    Database,
    GeneratedIntegerKeyInsertCommand,
    GreaterThan,
    OneOf,
    OrderBy,
    Query,
    TransactionMode,
)
from messaging.models import MessagingEvent, MessagingEventType, StreamEvent

_EVENT_ADAPTER = TypeAdapter(MessagingEvent)


class DatabaseEventStream:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def append(self, event: MessagingEvent) -> StreamEvent:
        validated = _EVENT_ADAPTER.validate_python(event)
        record = MessagingEventRecord(
            sequence=0, event_type=validated.event_type, document=validated.model_dump_json()
        )
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            sequence = await session.insert_generated_integer_key(
                EVENT_TABLE, GeneratedIntegerKeyInsertCommand(record, EVENT_SEQUENCE)
            )
        return StreamEvent(sequence=sequence, event=validated)

    async def list_after(self, sequence: int, limit: int) -> list[StreamEvent]:
        return await self.list_after_types(sequence, limit, ())

    async def list_after_types(
        self, sequence: int, limit: int, event_types: Sequence[MessagingEventType]
    ) -> list[StreamEvent]:
        if sequence < 0:
            raise ValueError("Event sequence cannot be negative")
        if limit < 0:
            raise ValueError("Event limit cannot be negative")
        predicates = [GreaterThan(EVENT_SEQUENCE, sequence)]
        if event_types:
            predicates.append(OneOf(EVENT_TYPE, tuple(event_types)))
        query = Query(
            filter=AllOf(tuple(predicates)),
            projection=AllFields(),
            ordering=OrderBy((EVENT_SEQUENCE,)),
            limit=limit,
        )
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            records = await session.find_many(EVENT_TABLE, query)
        return [
            StreamEvent(
                sequence=record.sequence, event=_EVENT_ADAPTER.validate_json(record.document)
            )
            for record in records
        ]

    async def close(self) -> None:
        return None
