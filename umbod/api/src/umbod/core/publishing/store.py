from typing import Protocol, runtime_checkable

from umbod.core.publishing.stores.events import (
    ConnectorPublishStateChanged,
    PublishState,
    PublishStateChangeSubscriber,
)


class ConnectorPublishingStore(Protocol):
    async def is_published(self, connector_id: str) -> bool: ...

    async def was_previously_published(self, connector_id: str) -> bool: ...

    async def publish_connector(self, connector_id: str) -> None: ...

    async def unpublish_connector(self, connector_id: str) -> None: ...

    async def delete_connector(self, connector_id: str) -> None: ...


@runtime_checkable
class ConnectorPublishStateChangeSource(Protocol):
    def subscribe_publish_state_changes(self, subscriber: PublishStateChangeSubscriber) -> None: ...


__all__ = [
    "ConnectorPublishingStore",
    "ConnectorPublishStateChanged",
    "ConnectorPublishStateChangeSource",
    "PublishState",
    "PublishStateChangeSubscriber",
]
