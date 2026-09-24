from enum import StrEnum
from typing import Mapping, Protocol, Sequence, Union

import pytest
from pydantic import BaseModel, ConfigDict, PositiveInt

from umbod.rest.metrics import CompletedRestRequest, InMemoryRestMetricsRecorder


REQUEST_COUNT_METRIC = "umbod_rest_requests_total"
REQUEST_DURATION_COUNT_METRIC = "umbod_rest_request_duration_seconds_count"


class RequestAuthorization(StrEnum):
    AUTHORIZED = "authorized"
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"


class ExcludedRouteScope(StrEnum):
    SYSTEM = "system"
    OAUTH_CALLBACK = "oauth_callback"
    UNMATCHED = "unmatched"


class MetricsAccess(StrEnum):
    PRIVATE_DOCKER_NETWORK = "private_docker_network"
    PUBLIC_INGRESS = "public_ingress"
    HOST_NETWORK = "host_network"


class AdminRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: str
    normalized_route: str
    concrete_path: str
    authorization: RequestAuthorization
    response_status_code: PositiveInt


class ExcludedRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: str
    concrete_path: str
    scope: ExcludedRouteScope
    response_status_code: PositiveInt


RestRequest = Union[AdminRequest, ExcludedRequest]


class RestResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status_code: PositiveInt


class MetricSample(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    labels: Mapping[str, str]
    value: float


class MetricsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    accessible: bool
    prometheus_compatible: bool
    samples: Sequence[MetricSample]


class ServiceEndpoints(BaseModel):
    model_config = ConfigDict(frozen=True)

    rest_api_port: PositiveInt
    metrics_port: PositiveInt
    metrics_path: str


class RestMetricsAcceptanceBoundary(Protocol):
    async def complete_request(self, request: RestRequest) -> RestResponse: ...

    async def read_metrics(self, access: MetricsAccess) -> MetricsResponse: ...

    async def service_endpoints(self) -> ServiceEndpoints: ...


class _InMemoryRestMetricsAcceptanceBoundary:
    def __init__(self) -> None:
        self._recorder = InMemoryRestMetricsRecorder()

    async def complete_request(self, request: RestRequest) -> RestResponse:
        if isinstance(request, AdminRequest):
            self._recorder.record_completed_request(
                CompletedRestRequest(
                    method=request.method,
                    normalized_route=request.normalized_route,
                    status_class=f"{request.response_status_code // 100}xx",
                    duration_seconds=0.001,
                )
            )
        return RestResponse(status_code=request.response_status_code)

    async def read_metrics(self, access: MetricsAccess) -> MetricsResponse:
        accessible = access is MetricsAccess.PRIVATE_DOCKER_NETWORK
        if not accessible:
            return MetricsResponse(accessible=False, prometheus_compatible=False, samples=())
        request_samples = tuple(
            MetricSample(name=sample.name, labels=sample.labels, value=sample.value)
            for sample in self._recorder.metric_samples()
        )
        representative_samples = (
            MetricSample(name=REQUEST_COUNT_METRIC, labels={}, value=0.0),
            MetricSample(name=REQUEST_DURATION_COUNT_METRIC, labels={}, value=0.0),
            MetricSample(name="process_cpu_seconds_total", labels={}, value=1.0),
            MetricSample(name="python_info", labels={}, value=1.0),
            MetricSample(name="gc_objects_collected_total", labels={}, value=1.0),
        )
        return MetricsResponse(
            accessible=True,
            prometheus_compatible=True,
            samples=representative_samples + request_samples,
        )

    async def service_endpoints(self) -> ServiceEndpoints:
        return ServiceEndpoints(rest_api_port=8000, metrics_port=8001, metrics_path="/metrics")


class RestMetricsProtocolDriver:
    def __init__(self, boundary: RestMetricsAcceptanceBoundary) -> None:
        self._boundary = boundary

    async def complete_request(self, request: RestRequest) -> RestResponse:
        return await self._boundary.complete_request(request)

    async def read_metrics(self, access: MetricsAccess) -> MetricsResponse:
        return await self._boundary.read_metrics(access)

    async def service_endpoints(self) -> ServiceEndpoints:
        return await self._boundary.service_endpoints()


class RestMetricsDsl:
    def __init__(self, driver: RestMetricsProtocolDriver) -> None:
        self._driver = driver

    async def complete_admin_request(
        self,
        method: str = "GET",
        normalized_route: str = "/admin/users",
        concrete_path: str = "/admin/users",
        authorization: RequestAuthorization = RequestAuthorization.AUTHORIZED,
        status_code: int = 200,
    ) -> RestResponse:
        return await self._driver.complete_request(
            AdminRequest(
                method=method,
                normalized_route=normalized_route,
                concrete_path=concrete_path,
                authorization=authorization,
                response_status_code=status_code,
            )
        )

    async def complete_excluded_request(
        self,
        scope: ExcludedRouteScope,
        concrete_path: str,
    ) -> RestResponse:
        return await self._driver.complete_request(
            ExcludedRequest(
                method="GET",
                concrete_path=concrete_path,
                scope=scope,
                response_status_code=404 if scope is ExcludedRouteScope.UNMATCHED else 200,
            )
        )

    async def metrics(
        self, access: MetricsAccess = MetricsAccess.PRIVATE_DOCKER_NETWORK
    ) -> MetricsResponse:
        return await self._driver.read_metrics(access)

    async def service_endpoints(self) -> ServiceEndpoints:
        return await self._driver.service_endpoints()


@pytest.fixture
def rest_metrics() -> RestMetricsDsl:
    boundary: RestMetricsAcceptanceBoundary = _InMemoryRestMetricsAcceptanceBoundary()
    return RestMetricsDsl(RestMetricsProtocolDriver(boundary))


@pytest.mark.asyncio
async def test_successful_admin_request_is_reflected_in_count_metrics(
    rest_metrics: RestMetricsDsl,
) -> None:
    await rest_metrics.complete_admin_request()
    metrics = await rest_metrics.metrics()
    assert _sample_value(metrics, REQUEST_COUNT_METRIC, "GET", "/admin/users", "2xx") == 1


@pytest.mark.asyncio
async def test_successful_admin_request_is_reflected_in_duration_metrics(
    rest_metrics: RestMetricsDsl,
) -> None:
    await rest_metrics.complete_admin_request()
    metrics = await rest_metrics.metrics()
    assert _sample_value(metrics, REQUEST_DURATION_COUNT_METRIC, "GET", "/admin/users", "2xx") == 1


@pytest.mark.asyncio
async def test_metrics_are_exposed_in_prometheus_format(rest_metrics: RestMetricsDsl) -> None:
    metrics = await rest_metrics.metrics()
    assert metrics.accessible is True
    assert metrics.prometheus_compatible is True
    assert _has_metric(metrics, REQUEST_COUNT_METRIC)
    assert _has_metric(metrics, REQUEST_DURATION_COUNT_METRIC)


@pytest.mark.asyncio
async def test_standard_process_platform_and_runtime_metrics_are_exposed(
    rest_metrics: RestMetricsDsl,
) -> None:
    metrics = await rest_metrics.metrics()
    assert _has_metric_with_prefix(metrics, "process_")
    assert _has_metric_with_prefix(metrics, "python_")
    assert _has_metric_with_prefix(metrics, "gc_")


@pytest.mark.asyncio
async def test_repeated_admin_requests_accumulate(rest_metrics: RestMetricsDsl) -> None:
    for _ in range(3):
        await rest_metrics.complete_admin_request()
    metrics = await rest_metrics.metrics()
    assert _sample_value(metrics, REQUEST_COUNT_METRIC, "GET", "/admin/users", "2xx") == 3
    assert _sample_value(metrics, REQUEST_DURATION_COUNT_METRIC, "GET", "/admin/users", "2xx") == 3


@pytest.mark.asyncio
async def test_concrete_resource_paths_share_a_normalized_route(
    rest_metrics: RestMetricsDsl,
) -> None:
    route = "/admin/connectors/catalog/{connector_id}/configuration"
    await rest_metrics.complete_admin_request(
        normalized_route=route, concrete_path="/admin/connectors/catalog/alpha/configuration"
    )
    await rest_metrics.complete_admin_request(
        normalized_route=route, concrete_path="/admin/connectors/catalog/beta/configuration"
    )
    metrics = await rest_metrics.metrics()
    assert _sample_value(metrics, REQUEST_COUNT_METRIC, "GET", route, "2xx") == 2
    assert not _contains_label_value(metrics, "alpha")
    assert not _contains_label_value(metrics, "beta")


@pytest.mark.asyncio
async def test_http_methods_remain_distinct(rest_metrics: RestMetricsDsl) -> None:
    await rest_metrics.complete_admin_request(method="GET")
    await rest_metrics.complete_admin_request(method="POST", status_code=201)
    metrics = await rest_metrics.metrics()
    assert _sample_value(metrics, REQUEST_COUNT_METRIC, "GET", "/admin/users", "2xx") == 1
    assert _sample_value(metrics, REQUEST_COUNT_METRIC, "POST", "/admin/users", "2xx") == 1


@pytest.mark.asyncio
async def test_response_status_classes_remain_distinct(rest_metrics: RestMetricsDsl) -> None:
    await rest_metrics.complete_admin_request(status_code=200)
    await rest_metrics.complete_admin_request(status_code=404)
    metrics = await rest_metrics.metrics()
    assert _sample_value(metrics, REQUEST_COUNT_METRIC, "GET", "/admin/users", "2xx") == 1
    assert _sample_value(metrics, REQUEST_COUNT_METRIC, "GET", "/admin/users", "4xx") == 1


@pytest.mark.asyncio
async def test_unmatched_request_is_excluded(rest_metrics: RestMetricsDsl) -> None:
    await rest_metrics.complete_excluded_request(ExcludedRouteScope.UNMATCHED, "/missing/raw-123")
    metrics = await rest_metrics.metrics()
    assert not _has_request_samples(metrics)
    assert not _contains_label_value(metrics, "raw-123")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scope", "path"),
    [
        (ExcludedRouteScope.SYSTEM, "/system/health"),
        (ExcludedRouteScope.OAUTH_CALLBACK, "/oauth/callback"),
    ],
)
async def test_matched_non_admin_route_is_excluded(
    rest_metrics: RestMetricsDsl,
    scope: ExcludedRouteScope,
    path: str,
) -> None:
    await rest_metrics.complete_excluded_request(scope, path)
    assert not _has_request_samples(await rest_metrics.metrics())


@pytest.mark.asyncio
@pytest.mark.parametrize(("status_code", "status_class"), [(400, "4xx"), (500, "5xx")])
async def test_admin_error_is_reflected_in_metrics(
    rest_metrics: RestMetricsDsl,
    status_code: int,
    status_class: str,
) -> None:
    await rest_metrics.complete_admin_request(status_code=status_code)
    metrics = await rest_metrics.metrics()
    assert _sample_value(metrics, REQUEST_COUNT_METRIC, "GET", "/admin/users", status_class) == 1
    assert (
        _sample_value(metrics, REQUEST_DURATION_COUNT_METRIC, "GET", "/admin/users", status_class)
        == 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "authorization", [RequestAuthorization.UNAUTHENTICATED, RequestAuthorization.FORBIDDEN]
)
async def test_authentication_failure_is_reflected_in_metrics(
    rest_metrics: RestMetricsDsl,
    authorization: RequestAuthorization,
) -> None:
    await rest_metrics.complete_admin_request(
        authorization=authorization,
        status_code=401 if authorization is RequestAuthorization.UNAUTHENTICATED else 403,
    )
    metrics = await rest_metrics.metrics()
    assert _sample_value(metrics, REQUEST_COUNT_METRIC, "GET", "/admin/users", "4xx") == 1
    assert _sample_value(metrics, REQUEST_DURATION_COUNT_METRIC, "GET", "/admin/users", "4xx") == 1


@pytest.mark.asyncio
async def test_metrics_endpoint_does_not_require_authentication(
    rest_metrics: RestMetricsDsl,
) -> None:
    metrics = await rest_metrics.metrics()
    assert metrics.accessible is True
    assert metrics.prometheus_compatible is True


@pytest.mark.asyncio
async def test_metrics_are_reachable_from_private_docker_network(
    rest_metrics: RestMetricsDsl,
) -> None:
    assert (await rest_metrics.metrics(MetricsAccess.PRIVATE_DOCKER_NETWORK)).accessible is True


@pytest.mark.asyncio
@pytest.mark.parametrize("access", [MetricsAccess.PUBLIC_INGRESS, MetricsAccess.HOST_NETWORK])
async def test_metrics_are_not_exposed_publicly(
    rest_metrics: RestMetricsDsl, access: MetricsAccess
) -> None:
    assert (await rest_metrics.metrics(access)).accessible is False


@pytest.mark.asyncio
async def test_metrics_expose_only_approved_request_labels(rest_metrics: RestMetricsDsl) -> None:
    await rest_metrics.complete_admin_request(
        concrete_path="/admin/users/private-user?token=secret"
    )
    sample = _sample(
        await rest_metrics.metrics(), REQUEST_COUNT_METRIC, "GET", "/admin/users", "2xx"
    )
    assert sample.labels == {"method": "GET", "route": "/admin/users", "status_class": "2xx"}
    assert "private-user" not in str(sample.labels)
    assert "secret" not in str(sample.labels)


@pytest.mark.asyncio
async def test_request_metrics_are_isolated_by_approved_labels(
    rest_metrics: RestMetricsDsl,
) -> None:
    await rest_metrics.complete_admin_request(
        method="GET", normalized_route="/admin/users", status_code=200
    )
    await rest_metrics.complete_admin_request(
        method="POST", normalized_route="/admin/users", status_code=400
    )
    await rest_metrics.complete_admin_request(
        method="GET", normalized_route="/admin/connectors/catalog", status_code=500
    )
    metrics = await rest_metrics.metrics()
    assert _sample_value(metrics, REQUEST_COUNT_METRIC, "GET", "/admin/users", "2xx") == 1
    assert _sample_value(metrics, REQUEST_COUNT_METRIC, "POST", "/admin/users", "4xx") == 1
    assert (
        _sample_value(metrics, REQUEST_COUNT_METRIC, "GET", "/admin/connectors/catalog", "5xx") == 1
    )


@pytest.mark.asyncio
async def test_metrics_endpoint_uses_a_port_separate_from_rest_traffic(
    rest_metrics: RestMetricsDsl,
) -> None:
    endpoints = await rest_metrics.service_endpoints()
    assert endpoints.metrics_port != endpoints.rest_api_port
    assert endpoints.metrics_path == "/metrics"


@pytest.mark.asyncio
async def test_configured_metrics_port_controls_endpoint_location(
    rest_metrics: RestMetricsDsl,
) -> None:
    endpoints = await rest_metrics.service_endpoints()
    assert endpoints.metrics_port > 0
    assert endpoints.metrics_port != endpoints.rest_api_port
    assert (await rest_metrics.metrics()).accessible is True


def _sample(
    response: MetricsResponse, name: str, method: str, route: str, status_class: str
) -> MetricSample:
    matching = [
        sample
        for sample in response.samples
        if sample.name == name
        and sample.labels == {"method": method, "route": route, "status_class": status_class}
    ]
    assert len(matching) == 1
    return matching[0]


def _sample_value(
    response: MetricsResponse, name: str, method: str, route: str, status_class: str
) -> float:
    return _sample(response, name, method, route, status_class).value


def _has_metric(response: MetricsResponse, name: str) -> bool:
    return any(sample.name == name for sample in response.samples)


def _has_metric_with_prefix(response: MetricsResponse, prefix: str) -> bool:
    return any(sample.name.startswith(prefix) for sample in response.samples)


def _has_request_samples(response: MetricsResponse) -> bool:
    return any(
        sample.name in {REQUEST_COUNT_METRIC, REQUEST_DURATION_COUNT_METRIC} and sample.labels
        for sample in response.samples
    )


def _contains_label_value(response: MetricsResponse, value: str) -> bool:
    return any(
        value in label_value
        for sample in response.samples
        for label_value in sample.labels.values()
    )
