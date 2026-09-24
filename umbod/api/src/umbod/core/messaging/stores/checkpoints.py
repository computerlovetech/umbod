from umbod.core.messaging.stores.schema import (
    CHECKPOINT_CONSUMER_ID,
    CHECKPOINT_TABLE,
    MessagingCheckpointKey,
    MessagingCheckpointRecord,
)
from umbod.core.persistence import (
    AllFields,
    Database,
    Equals,
    Query,
    TransactionMode,
    Unordered,
    UpsertCommand,
)


class DatabaseEventCheckpointStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def get_last_processed_sequence(self, consumer_id: str) -> int:
        query = Query(
            filter=Equals(CHECKPOINT_CONSUMER_ID, consumer_id),
            projection=AllFields(),
            ordering=Unordered(),
        )
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            record = await session.find_one(CHECKPOINT_TABLE, query)
        return 0 if record is None else record.sequence

    async def save_last_processed_sequence(self, consumer_id: str, sequence: int) -> None:
        if sequence < 0:
            raise ValueError("Checkpoint sequence cannot be negative")
        query = Query(
            filter=Equals(CHECKPOINT_CONSUMER_ID, consumer_id),
            projection=AllFields(),
            ordering=Unordered(),
        )
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            existing = await session.find_one(CHECKPOINT_TABLE, query)
            if existing is not None and sequence < existing.sequence:
                raise ValueError("Cannot save a lower checkpoint sequence")
            record = MessagingCheckpointRecord(consumer_id=consumer_id, sequence=sequence)
            await session.upsert(
                CHECKPOINT_TABLE,
                UpsertCommand(key=MessagingCheckpointKey(consumer_id=consumer_id), row=record),
            )

    async def close(self) -> None:
        return None
