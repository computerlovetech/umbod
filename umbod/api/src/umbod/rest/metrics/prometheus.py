from prometheus_client import CollectorRegistry, Counter, GCCollector, Histogram
from prometheus_client import PlatformCollector, ProcessCollector, generate_latest

from umbod.rest.metrics.models import CompletedRestRequest


REQUEST_LABELS = ("method", "route", "status_class")


class PrometheusRestMetricsRecorder:
    def __init__(self) -> None:
        self._registry = CollectorRegistry()
        ProcessCollector(registry=self._registry)
        PlatformCollector(registry=self._registry)
        GCCollector(registry=self._registry)
        self._requests = Counter(
            "umbod_rest_requests_total",
            "Completed REST requests",
            REQUEST_LABELS,
            registry=self._registry,
        )
        self._request_duration = Histogram(
            "umbod_rest_request_duration_seconds",
            "Completed REST request duration in seconds",
            REQUEST_LABELS,
            registry=self._registry,
        )

    def record_completed_request(self, request: CompletedRestRequest) -> None:
        labels = {
            "method": request.method,
            "route": request.normalized_route,
            "status_class": request.status_class,
        }
        self._requests.labels(**labels).inc()
        self._request_duration.labels(**labels).observe(request.duration_seconds)

    def prometheus_text(self) -> bytes:
        return generate_latest(self._registry)
