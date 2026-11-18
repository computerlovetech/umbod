import subprocess
import sys
from importlib import import_module

import pytest

import umbod.infrastructure as infrastructure


def test_importing_infrastructure_does_not_load_metrics_or_asgi_implementations() -> None:
    command = (
        "import sys; import umbod.infrastructure; "
        "blocked = ('umbod.infrastructure.metrics', 'prometheus_client', "
        "'fastapi', 'starlette', 'uvicorn'); "
        "assert not [name for name in sys.modules "
        "if any(name == prefix or name.startswith(prefix + '.') for prefix in blocked)]"
    )
    result = subprocess.run(
        [sys.executable, "-c", command], check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("name", "module_name"),
    [
        ("create_mcp_metrics", "umbod.infrastructure.metrics.mcp.composition"),
        ("create_rest_metrics_recorder", "umbod.infrastructure.metrics.rest.composition"),
        ("create_rest_metrics_http_server", "umbod.infrastructure.metrics.rest.composition"),
        ("create_telemetry_app", "umbod.infrastructure.metrics.collector.composition"),
        ("create_receiver_app_with_registry", "umbod.infrastructure.metrics.collector.composition"),
        ("install_telemetry_receiver", "umbod.infrastructure.metrics.collector.composition"),
    ],
)
def test_public_metrics_factories_preserve_original_identity(name: str, module_name: str) -> None:
    exported = getattr(infrastructure, name)
    assert exported is getattr(import_module(module_name), name)
    assert getattr(infrastructure, name) is exported


def test_unknown_infrastructure_export_raises_attribute_error() -> None:
    with pytest.raises(AttributeError, match="has no attribute 'PrometheusRestMetricsRecorder'"):
        getattr(infrastructure, "PrometheusRestMetricsRecorder")
