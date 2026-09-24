from typing import Iterable

from prometheus_client.parser import text_string_to_metric_families
from prometheus_client.samples import Sample

from umbod.rest.metrics import (
    CompletedRestRequest,
    PrometheusRestMetricsRecorder,
    RestMetricsRecorder,
)


def _record_request(
    recorder: RestMetricsRecorder,
    method: str = "GET",
    route: str = "/admin/users",
    status_class: str = "2xx",
    duration_seconds: float = 0.25,
) -> None:
    recorder.record_completed_request(
        CompletedRestRequest.model_validate(
            {
                "method": method,
                "normalized_route": route,
                "status_class": status_class,
                "duration_seconds": duration_seconds,
            }
        )
    )


def _samples(text: bytes) -> dict[str, tuple[Sample, ...]]:
    families: Iterable[object] = text_string_to_metric_families(text.decode("utf-8"))
    return {family.name: tuple(family.samples) for family in families}


def _sample(
    samples: dict[str, tuple[Sample, ...]],
    family_name: str,
    sample_name: str,
    labels: dict[str, str],
) -> Sample:
    return next(
        sample
        for sample in samples[family_name]
        if sample.name == sample_name and sample.labels == labels
    )


def test_prometheus_recorder_records_aggregated_count_and_duration_through_protocol() -> None:
    recorder = PrometheusRestMetricsRecorder()
    _record_request(recorder, duration_seconds=0.25)
    _record_request(recorder, duration_seconds=0.75)

    samples = _samples(recorder.prometheus_text())
    labels = {"method": "GET", "route": "/admin/users", "status_class": "2xx"}

    assert (
        _sample(
            samples,
            "umbod_rest_requests",
            "umbod_rest_requests_total",
            labels,
        ).value
        == 2
    )
    assert (
        _sample(
            samples,
            "umbod_rest_request_duration_seconds",
            "umbod_rest_request_duration_seconds_count",
            labels,
        ).value
        == 2
    )
    assert (
        _sample(
            samples,
            "umbod_rest_request_duration_seconds",
            "umbod_rest_request_duration_seconds_sum",
            labels,
        ).value
        == 1
    )


def test_prometheus_recorder_uses_only_approved_labels() -> None:
    recorder = PrometheusRestMetricsRecorder()
    _record_request(
        recorder,
        method="POST",
        route="/admin/connectors/catalog/{connector_id}",
        status_class="4xx",
    )

    samples = _samples(recorder.prometheus_text())
    expected_labels = {
        "method": "POST",
        "route": "/admin/connectors/catalog/{connector_id}",
        "status_class": "4xx",
    }

    request_samples = samples["umbod_rest_requests"]
    duration_samples = samples["umbod_rest_request_duration_seconds"]
    assert all(sample.labels == expected_labels for sample in request_samples)
    assert all(
        sample.labels == expected_labels or "le" in sample.labels for sample in duration_samples
    )
    assert all(
        set(sample.labels) == {"method", "route", "status_class", "le"}
        for sample in duration_samples
        if "le" in sample.labels
    )


def test_prometheus_recorder_exposes_process_platform_and_gc_collectors() -> None:
    recorder = PrometheusRestMetricsRecorder()

    samples = _samples(recorder.prometheus_text())
    sample_names = {sample.name for family_samples in samples.values() for sample in family_samples}

    assert "python_info" in sample_names
    assert any(name.startswith("python_gc_") for name in sample_names)


def test_prometheus_recorder_registry_is_instance_local() -> None:
    first_recorder = PrometheusRestMetricsRecorder()
    second_recorder = PrometheusRestMetricsRecorder()
    _record_request(first_recorder)

    first_samples = _samples(first_recorder.prometheus_text())
    second_samples = _samples(second_recorder.prometheus_text())

    assert first_samples["umbod_rest_requests"]
    assert second_samples["umbod_rest_requests"] == ()
    assert second_samples["umbod_rest_request_duration_seconds"] == ()
