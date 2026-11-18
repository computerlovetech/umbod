from umbod.infrastructure.metrics.rest.http_server import RestMetricsHttpServer
from umbod.infrastructure.metrics.rest.prometheus import PrometheusRestMetricsRecorder
from umbod.rest.metrics.recorder import RestMetricsExposer


def create_rest_metrics_recorder() -> PrometheusRestMetricsRecorder:
    return PrometheusRestMetricsRecorder()


def create_rest_metrics_http_server(recorder: RestMetricsExposer, port: int) -> RestMetricsHttpServer:
    return RestMetricsHttpServer(recorder, port)
