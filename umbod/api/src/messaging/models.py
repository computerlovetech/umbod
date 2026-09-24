from datetime import datetime, timezone
from typing import Literal

from pydantic import ConfigDict, Field
from messaging.proxies import Model

MessagingEventType = Literal[
    "connector.publication.changed",
    "connector.configuration.changed",
    "connector.capability_activation.changed",
    "connector.invocation_policy.changed",
    "connector.capability_description_override.changed",
    "mcp.group_permission.changed",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MessagingEvent(Model):
    model_config = ConfigDict(extra="forbid")

    event_type: MessagingEventType
    subject: str
    metadata: dict[str, str] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=utc_now)


class StreamEvent(Model):
    model_config = ConfigDict(extra="forbid")

    sequence: int
    event: MessagingEvent
