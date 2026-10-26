from typing import Generic, TypeVar

from .ports import SignalFailureHandler, SignalReceiver

EventT = TypeVar("EventT")


class Signal(Generic[EventT]):
    def __init__(self, failure_handler: SignalFailureHandler) -> None:
        self._failure_handler = failure_handler
        self._receivers: dict[str, SignalReceiver[EventT]] = {}

    def connect(self, receiver_name: str, receiver: SignalReceiver[EventT]) -> None:
        if receiver_name in self._receivers:
            if self._receivers[receiver_name] is receiver:
                return
            raise ValueError(f"Signal receiver name already registered: {receiver_name}")
        self._receivers[receiver_name] = receiver

    def is_connected(self, receiver_name: str) -> bool:
        return receiver_name in self._receivers

    def send(self, event: EventT) -> None:
        for receiver_name, receiver in tuple(self._receivers.items()):
            try:
                receiver(event)
            except Exception as error:
                try:
                    self._failure_handler.handles(receiver_name, error)
                except Exception:
                    pass
