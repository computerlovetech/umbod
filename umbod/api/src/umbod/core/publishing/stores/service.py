from datetime import UTC, datetime

from umbod.core.publishing.stores.events import (
    ConnectorPublishStateChanged,
    PublishStateChangeSubscriber,
)
from umbod.core.publishing.stores.schema import (
    PUBLICATION_STATE_CONNECTOR_ID,
    PUBLICATION_STATE_PROJECTION,
    PublicationStateKey,
    PublicationStateRecord,
    PublicationStateResult,
    PublicationStateWrite,
)
from umbod.core.persistence import (
    TransactionMode,
    Database,
    DatabaseSession,
    DeleteQuery,
    Equals,
    Query,
    Table,
    Unordered,
    UpsertCommand,
)


class ConnectorPublishingStoreService:
    def __init__(
        self,
        database: Database,
        publication_states: Table[PublicationStateRecord, PublicationStateKey],
    ) -> None:
        self._database = database
        self._publication_states = publication_states
        self._publish_state_change_subscribers: list[PublishStateChangeSubscriber] = []

    async def is_published(self, connector_id: str) -> bool:
        state = await self._publication_state(connector_id)
        return state.published if state is not None else False

    async def was_previously_published(self, connector_id: str) -> bool:
        state = await self._publication_state(connector_id)
        return state.previously_published if state is not None else False

    async def publish_connector(self, connector_id: str) -> None:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            state = await self._find_publication_state(session, connector_id)
            write = PublicationStateWrite(
                published=True,
                previously_published=True,
                revision=1 if state is None else state.revision + 1,
                updated_at=_updated_at(),
            )
            await self._upsert_publication_state(session, connector_id, write)
        await self._publish_state_changed(
            ConnectorPublishStateChanged(connector_id=connector_id, state="published")
        )

    async def unpublish_connector(self, connector_id: str) -> None:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            state = await self._find_publication_state(session, connector_id)
            if state is not None:
                write = PublicationStateWrite(
                    published=False,
                    previously_published=state.previously_published or state.published,
                    revision=state.revision + 1,
                    updated_at=_updated_at(),
                )
                await self._upsert_publication_state(session, connector_id, write)
        await self._publish_state_changed(
            ConnectorPublishStateChanged(connector_id=connector_id, state="unpublished")
        )

    async def delete_connector(self, connector_id: str) -> None:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await session.delete(
                self._publication_states,
                DeleteQuery(Equals(PUBLICATION_STATE_CONNECTOR_ID, connector_id)),
            )

    def subscribe_publish_state_changes(self, subscriber: PublishStateChangeSubscriber) -> None:
        self._publish_state_change_subscribers.append(subscriber)

    async def _publication_state(self, connector_id: str) -> PublicationStateResult | None:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            return await self._find_publication_state(session, connector_id)

    async def _find_publication_state(
        self, session: DatabaseSession, connector_id: str
    ) -> PublicationStateResult | None:
        return await session.find_one(
            self._publication_states,
            Query(
                filter=Equals(PUBLICATION_STATE_CONNECTOR_ID, connector_id),
                projection=PUBLICATION_STATE_PROJECTION,
                ordering=Unordered(),
            ),
        )

    async def _upsert_publication_state(
        self, session: DatabaseSession, connector_id: str, write: PublicationStateWrite
    ) -> None:
        await session.upsert(
            self._publication_states,
            UpsertCommand(
                key=PublicationStateKey(connector_id=connector_id),
                row=PublicationStateRecord(connector_id=connector_id, **write.model_dump()),
            ),
        )

    async def _publish_state_changed(self, event: ConnectorPublishStateChanged) -> None:
        for subscriber in self._publish_state_change_subscribers:
            await subscriber(event)


def _updated_at() -> str:
    return datetime.now(UTC).isoformat()
