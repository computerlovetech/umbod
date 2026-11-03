from prometheus_client import CollectorRegistry, Counter, Histogram

from umbod.rest.telemetry.observations import AcceptedCollectorLogs, CompletedCollectorRequest


class PrometheusCollectorMetrics:
    def __init__(self, registry: CollectorRegistry) -> None:
        labels = ("method", "route", "status_class")
        self._requests = Counter(
            "umbod_collector_requests_total", "Completed collector requests",
            labels, registry=registry,
        )
        self._duration = Histogram(
            "umbod_collector_request_duration_seconds",
            "Completed collector request duration in seconds", labels, registry=registry,
        )
        self._accepted_logs = Counter(
            "umbod_collector_log_records_accepted_total",
            "Log records accepted after all required ingestion operations succeed",
            registry=registry,
        )

    def record_request(self, event: CompletedCollectorRequest) -> None:
        labels = (event.method, event.route, event.status_class)
        self._requests.labels(*labels).inc()
        self._duration.labels(*labels).observe(event.duration_seconds)

    def record_logs(self, event: AcceptedCollectorLogs) -> None:
        self._accepted_logs.inc(event.record_count)
