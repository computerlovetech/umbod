import asyncio
from dataclasses import FrozenInstanceError, dataclass
from typing import Protocol

import pytest

from umbod.core.signals import (
    InMemorySignalFailureHandler,
    Signal,
    SignalFailureHandler,
    SignalPublisher,
    SignalReceiver,
    SignalReceiverFailure,
)


@dataclass(frozen=True)
class DocumentPublished:
    document_id: str


class DocumentSignal(SignalPublisher[DocumentPublished], Protocol):
    def connect(
        self, receiver_name: str, receiver: SignalReceiver[DocumentPublished]
    ) -> None: ...


@pytest.fixture
def failure_handler() -> InMemorySignalFailureHandler:
    return InMemorySignalFailureHandler()


@pytest.fixture
def signal(failure_handler: InMemorySignalFailureHandler) -> DocumentSignal:
    handler: SignalFailureHandler = failure_handler
    return Signal[DocumentPublished](failure_handler=handler)


def test_send_without_receivers_returns_none(signal: DocumentSignal) -> None:
    assert signal.send(DocumentPublished(document_id="document")) is None


def test_custom_event_reaches_receivers_in_registration_order(
    signal: DocumentSignal,
) -> None:
    received: list[tuple[str, DocumentPublished]] = []

    def first(event: DocumentPublished) -> None:
        received.append(("first", event))

    def second(event: DocumentPublished) -> None:
        received.append(("second", event))

    signal.connect("first", first)
    signal.connect("second", second)
    event = DocumentPublished(document_id="document")
    publisher: SignalPublisher[DocumentPublished] = signal
    publisher.send(event)

    assert received == [("first", event), ("second", event)]


def test_app_scoped_signals_do_not_share_registration(
    signal: DocumentSignal, failure_handler: InMemorySignalFailureHandler
) -> None:
    other: SignalPublisher[DocumentPublished] = Signal[DocumentPublished](failure_handler)
    received: list[DocumentPublished] = []
    signal.connect("receiver", received.append)

    other.send(DocumentPublished(document_id="other-app"))

    assert received == []


def test_repeated_receiver_registration_is_idempotent(signal: DocumentSignal) -> None:
    received: list[DocumentPublished] = []
    receiver: SignalReceiver[DocumentPublished] = received.append
    signal.connect("receiver", receiver)
    signal.connect("receiver", receiver)
    event = DocumentPublished(document_id="document")

    signal.send(event)

    assert received == [event]


def test_conflicting_registration_preserves_original_receiver(
    signal: DocumentSignal,
) -> None:
    original: list[DocumentPublished] = []
    replacement: list[DocumentPublished] = []
    signal.connect("receiver", original.append)

    with pytest.raises(ValueError, match="receiver"):
        signal.connect("receiver", replacement.append)
    event = DocumentPublished(document_id="document")
    signal.send(event)

    assert original == [event]
    assert replacement == []


def test_same_receiver_can_be_registered_under_distinct_names(
    signal: DocumentSignal,
) -> None:
    received: list[DocumentPublished] = []
    receiver: SignalReceiver[DocumentPublished] = received.append
    signal.connect("first", receiver)
    signal.connect("second", receiver)
    event = DocumentPublished(document_id="document")

    signal.send(event)

    assert received == [event, event]


def test_receiver_failure_is_recorded_without_stopping_delivery(
    signal: DocumentSignal, failure_handler: InMemorySignalFailureHandler
) -> None:
    received: list[DocumentPublished] = []
    error = ValueError("receiver failure")

    def failing_receiver(event: DocumentPublished) -> None:
        raise error

    signal.connect("failing", failing_receiver)
    signal.connect("healthy", received.append)
    event = DocumentPublished(document_id="document")

    result = signal.send(event)

    assert result is None
    assert received == [event]
    assert failure_handler.failures == (
        SignalReceiverFailure(receiver_name="failing", error=error),
    )


def test_failure_handler_failure_does_not_stop_later_receivers() -> None:
    failures: list[str] = []

    class FailingHandler:
        def handles(self, receiver_name: str, error: Exception) -> None:
            failures.append(receiver_name)
            raise RuntimeError("failure handler failed")

    handler: SignalFailureHandler = FailingHandler()
    signal: DocumentSignal = Signal[DocumentPublished](handler)
    received: list[DocumentPublished] = []

    def failing_receiver(event: DocumentPublished) -> None:
        raise ValueError("receiver failed")

    signal.connect("first-failure", failing_receiver)
    signal.connect("second-failure", failing_receiver)
    signal.connect("healthy", received.append)
    event = DocumentPublished(document_id="document")

    assert signal.send(event) is None
    assert received == [event]
    assert failures == ["first-failure", "second-failure"]


def test_receivers_registered_during_send_start_on_next_send(
    signal: DocumentSignal,
) -> None:
    received: list[tuple[str, DocumentPublished]] = []

    def late_receiver(event: DocumentPublished) -> None:
        received.append(("late", event))

    def registering_receiver(event: DocumentPublished) -> None:
        received.append(("registering", event))
        signal.connect("late", late_receiver)

    signal.connect("registering", registering_receiver)
    first = DocumentPublished(document_id="first")
    second = DocumentPublished(document_id="second")

    signal.send(first)
    signal.send(second)

    assert received == [("registering", first), ("registering", second), ("late", second)]


@pytest.mark.parametrize("error_type", [KeyboardInterrupt, SystemExit, asyncio.CancelledError])
def test_receiver_base_exception_propagates(
    signal: DocumentSignal,
    failure_handler: InMemorySignalFailureHandler,
    error_type: type[BaseException],
) -> None:
    error = error_type()
    received: list[DocumentPublished] = []

    def interrupted_receiver(event: DocumentPublished) -> None:
        raise error

    signal.connect("interrupted", interrupted_receiver)
    signal.connect("later", received.append)

    with pytest.raises(error_type) as raised:
        signal.send(DocumentPublished(document_id="document"))

    assert raised.value is error
    assert failure_handler.failures == ()
    assert received == []


@pytest.mark.parametrize("error_type", [KeyboardInterrupt, SystemExit, asyncio.CancelledError])
def test_failure_handler_base_exception_propagates(
    error_type: type[BaseException],
) -> None:
    error = error_type()

    class InterruptedHandler:
        def handles(self, receiver_name: str, error: Exception) -> None:
            raise interruption

    interruption = error
    handler: SignalFailureHandler = InterruptedHandler()
    signal: DocumentSignal = Signal[DocumentPublished](handler)

    def failing_receiver(event: DocumentPublished) -> None:
        raise ValueError("receiver failed")

    signal.connect("failing", failing_receiver)

    with pytest.raises(error_type) as raised:
        signal.send(DocumentPublished(document_id="document"))

    assert raised.value is error


def test_failure_records_are_immutable_snapshots(
    failure_handler: InMemorySignalFailureHandler,
) -> None:
    handler: SignalFailureHandler = failure_handler
    first_error = ValueError("first")
    handler.handles("first", first_error)
    snapshot = failure_handler.failures
    handler.handles("second", RuntimeError("second"))

    assert snapshot == (SignalReceiverFailure(receiver_name="first", error=first_error),)
    assert len(failure_handler.failures) == 2
    with pytest.raises(FrozenInstanceError):
        setattr(snapshot[0], "receiver_name", "changed")
