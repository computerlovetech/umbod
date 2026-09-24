from typing import cast

import pytest
from pydantic import ValidationError

from umbod.rest.metrics import CompletedRestRequest, RestMetricsRecorder


class RecordingRestMetricsRecorder:
    def __init__(self) -> None:
        self.completed_requests: list[CompletedRestRequest] = []

    def record_completed_request(self, request: CompletedRestRequest) -> None:
        self.completed_requests.append(request)


def _record_completed_request(recorder: RestMetricsRecorder, request: CompletedRestRequest) -> None:
    recorder.record_completed_request(request)


def test_rest_metrics_recorder_accepts_completed_request_contract() -> None:
    recorder = RecordingRestMetricsRecorder()
    request = CompletedRestRequest(
        method="GET",
        normalized_route="/admin/connectors/catalog/{connector_id}",
        status_class="2xx",
        duration_seconds=0.01,
    )

    _record_completed_request(recorder, request)

    assert recorder.completed_requests == [request]


def test_completed_rest_request_is_immutable() -> None:
    request = CompletedRestRequest(
        method="GET",
        normalized_route="/admin/users",
        status_class="2xx",
        duration_seconds=0.01,
    )

    with pytest.raises(ValidationError):
        request.method = cast(str, "POST")


@pytest.mark.parametrize("duration_seconds", [0, -0.01])
def test_completed_rest_request_rejects_non_positive_duration(duration_seconds: float) -> None:
    with pytest.raises(ValidationError):
        CompletedRestRequest(
            method="GET",
            normalized_route="/admin/users",
            status_class="2xx",
            duration_seconds=duration_seconds,
        )


def test_completed_rest_request_rejects_raw_or_sensitive_fields() -> None:
    with pytest.raises(ValidationError):
        CompletedRestRequest.model_validate(
            {
                "method": "GET",
                "normalized_route": "/admin/users",
                "status_class": "2xx",
                "duration_seconds": 0.01,
                "raw_path": "/admin/users/private-user?token=secret",
            }
        )
