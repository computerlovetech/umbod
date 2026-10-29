from umbod.core.signals.models import SignalReceiverFailure


class InMemorySignalFailureHandler:
    def __init__(self) -> None:
        self._failures: list[SignalReceiverFailure] = []

    @property
    def failures(self) -> tuple[SignalReceiverFailure, ...]:
        return tuple(self._failures)

    def handles(self, receiver_name: str, error: Exception) -> None:
        self._failures.append(
            SignalReceiverFailure(receiver_name=receiver_name, error=error)
        )
