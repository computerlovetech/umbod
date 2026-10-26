from dataclasses import dataclass


@dataclass(frozen=True)
class SignalReceiverFailure:
    receiver_name: str
    error: Exception
