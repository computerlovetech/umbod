from collections.abc import Callable
from typing import Protocol, TypeAlias, TypeVar

EventT = TypeVar("EventT")
EventT_contra = TypeVar("EventT_contra", contravariant=True)

SignalReceiver: TypeAlias = Callable[[EventT], None]


class SignalPublisher(Protocol[EventT_contra]):
    def send(self, event: EventT_contra) -> None: ...


class SignalFailureHandler(Protocol):
    def handles(self, receiver_name: str, error: Exception) -> None: ...
