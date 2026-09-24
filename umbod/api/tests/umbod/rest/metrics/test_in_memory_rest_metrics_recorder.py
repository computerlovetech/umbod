from umbod.rest.metrics import (
    CompletedRestRequest,
    InMemoryRestMetricsRecorder,
    RestMetricSample,
    RestMetricsRecorder,
)


REQUEST_COUNT_METRIC = "umbod_rest_requests_total"
REQUEST_DURATION_COUNT_METRIC = "umbod_rest_request_duration_seconds_count"


def _recorder() -> RestMetricsRecorder:
    return InMemoryRestMetricsRecorder()


def _request(
    method: str = "GET",
    normalized_route: str = "/admin/users",
    status_class: str = "2xx",
) -> CompletedRestRequest:
    return CompletedRestRequest.model_validate(
        {
            "method": method,
            "normalized_route": normalized_route,
            "status_class": status_class,
            "duration_seconds": 0.01,
        }
    )


def _sample(
    samples: tuple[RestMetricSample, ...],
    name: str,
    method: str,
    route: str,
    status_class: str,
) -> RestMetricSample:
    return next(
        sample
        for sample in samples
        if sample.name == name
        and sample.labels == {"method": method, "route": route, "status_class": status_class}
    )


def test_completed_requests_aggregate_by_approved_dimensions() -> None:
    recorder = _recorder()
    recorder.record_completed_request(_request())
    recorder.record_completed_request(_request())
    recorder.record_completed_request(_request(method="POST"))
    recorder.record_completed_request(_request(normalized_route="/admin/connectors/catalog"))
    recorder.record_completed_request(_request(status_class="4xx"))

    samples = recorder.metric_samples()

    assert _sample(samples, REQUEST_COUNT_METRIC, "GET", "/admin/users", "2xx").value == 2
    assert _sample(samples, REQUEST_COUNT_METRIC, "POST", "/admin/users", "2xx").value == 1
    assert (
        _sample(samples, REQUEST_COUNT_METRIC, "GET", "/admin/connectors/catalog", "2xx").value == 1
    )
    assert _sample(samples, REQUEST_COUNT_METRIC, "GET", "/admin/users", "4xx").value == 1


def test_completed_requests_expose_count_and_duration_count_samples() -> None:
    recorder = _recorder()
    recorder.record_completed_request(_request())

    samples = recorder.metric_samples()

    assert _sample(samples, REQUEST_COUNT_METRIC, "GET", "/admin/users", "2xx").value == 1
    assert _sample(samples, REQUEST_DURATION_COUNT_METRIC, "GET", "/admin/users", "2xx").value == 1
    assert all(set(sample.labels) == {"method", "route", "status_class"} for sample in samples)


def test_recorder_state_is_instance_local() -> None:
    first_recorder = _recorder()
    second_recorder = _recorder()
    first_recorder.record_completed_request(_request())

    assert len(first_recorder.metric_samples()) == 2
    assert second_recorder.metric_samples() == ()
