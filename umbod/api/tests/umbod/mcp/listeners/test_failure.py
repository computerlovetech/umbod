import json

import pytest

from umbod.logging import OpenTelemetryJsonFormatter
from umbod.logging import LoggingSignalFailureHandler


def test_signal_failure_omits_receiver_and_exception_messages(
    caplog: pytest.LogCaptureFixture,
) -> None:
    try:
        raise RuntimeError("secret-canary-error")
    except RuntimeError as error:
        LoggingSignalFailureHandler().handles("secret-canary-receiver", error)

    assert len(caplog.records) == 1
    serialized = OpenTelemetryJsonFormatter("test").format(caplog.records[0])
    payload = json.loads(serialized)
    assert "secret-canary" not in serialized
    assert payload["body"] == "Signal receiver failed"
    assert payload["attributes"]["exception.type"] == "RuntimeError"
    assert payload["attributes"]["operation"] == "deliver_signal"
    assert "test_signal_failure" in payload["attributes"]["exception.stacktrace"]
