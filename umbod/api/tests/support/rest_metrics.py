from collections import defaultdict
from typing import DefaultDict

from umbod.rest.metrics.models import CompletedRestRequest, RestMetricSample


REQUEST_COUNT_METRIC = "umbod_rest_requests_total"
REQUEST_DURATION_COUNT_METRIC = "umbod_rest_request_duration_seconds_count"


class InMemoryRestMetricsRecorder:
    def __init__(self) -> None:
        self._request_counts: DefaultDict[tuple[str, str, str], int] = defaultdict(int)

    def record_completed_request(self, request: CompletedRestRequest) -> None:
        key = (request.method, request.normalized_route, request.status_class)
        self._request_counts[key] += 1

    def metric_samples(self) -> tuple[RestMetricSample, ...]:
        samples: list[RestMetricSample] = []
        for (method, route, status_class), count in self._request_counts.items():
            labels = {
                "method": method,
                "route": route,
                "status_class": status_class,
            }
            samples.extend(
                (
                    RestMetricSample(
                        name=REQUEST_COUNT_METRIC,
                        labels=labels,
                        value=float(count),
                    ),
                    RestMetricSample(
                        name=REQUEST_DURATION_COUNT_METRIC,
                        labels=labels,
                        value=float(count),
                    ),
                )
            )
        return tuple(samples)
