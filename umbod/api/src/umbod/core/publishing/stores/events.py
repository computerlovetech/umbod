from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

PublishState = Literal["published", "unpublished"]
PublishStateChangeSubscriber = Callable[["ConnectorPublishStateChanged"], Awaitable[None]]


@dataclass(frozen=True)
class ConnectorPublishStateChanged:
    connector_id: str
    state: PublishState
