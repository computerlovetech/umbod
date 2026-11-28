from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from umbod.infrastructure.telemetry.backfill_composition import create_log_archive_backfill
    from umbod.infrastructure.telemetry.replay_composition import (
        create_log_archive_replay,
        create_log_archive_replay_with_normalizer,
    )
    from umbod.infrastructure.http import OutboundHttpClientFactory, OutboundHttpClientOptions
    from umbod.infrastructure.mcp_endpoint_access import open_anonymous_mcp_initialization
    from umbod.infrastructure.mcp_registry import open_official_mcp_registry
    from umbod.infrastructure.metrics.mcp.composition import create_mcp_metrics
    from umbod.infrastructure.metrics.rest.composition import (
        create_rest_metrics_recorder,
        create_rest_metrics_http_server,
    )
    from umbod.infrastructure.metrics.collector.composition import (
        create_telemetry_app,
        create_receiver_app_with_registry,
        install_telemetry_receiver,
    )
    from umbod.infrastructure.portable_connectors import open_portable_draft_validator

from umbod.infrastructure.key_value import create_inmemory_key_value_driver, create_request_cache
from umbod.infrastructure.telemetry import (
    create_configured_analytics_runtime,
    create_disabled_analytics_runtime,
    create_sqlite_analytics_runtime,
)
from umbod.infrastructure.persistence.runtime import (
    AppPersistenceRuntime,
    ConfiguredPersistenceRuntimeProvider,
)
from umbod.infrastructure.filesystem.migration import migrate_local_content
from umbod.infrastructure.filesystem import (
    ContentConfig,
    InMemoryContentConfig,
    LocalContentConfig,
    S3ContentConfig,
    FilesystemConfig,
    create_access_control_driver,
    create_filesystem_namespaces,
    create_filesystem_namespace_management,
    create_filesystem_homes,
    create_filesystem_access,
    create_filesystem_browsing,
    create_filesystem_explorer,
    create_filesystem_sharing,
    create_filesystem_transactions,
    create_filesystem_creation,
    create_filesystem_uploads,
    create_content_driver,
    create_namespace_driver,
    create_filesystem,
)

__all__ = [
    "OutboundHttpClientFactory",
    "OutboundHttpClientOptions",
    "open_anonymous_mcp_initialization",
    "open_official_mcp_registry",
    "create_mcp_metrics",
    "create_rest_metrics_recorder",
    "create_rest_metrics_http_server",
    "create_telemetry_app",
    "create_receiver_app_with_registry",
    "install_telemetry_receiver",
    "migrate_local_content",
    "create_log_archive_backfill",
    "create_log_archive_replay",
    "create_log_archive_replay_with_normalizer",
    "create_configured_analytics_runtime",
    "create_disabled_analytics_runtime",
    "create_sqlite_analytics_runtime",
    "create_inmemory_key_value_driver",
    "create_request_cache",
    "AppPersistenceRuntime",
    "ConfiguredPersistenceRuntimeProvider",
    "ContentConfig",
    "InMemoryContentConfig",
    "LocalContentConfig",
    "S3ContentConfig",
    "FilesystemConfig",
    "create_access_control_driver",
    "create_filesystem_namespaces",
    "create_filesystem_namespace_management",
    "create_filesystem_homes",
    "create_filesystem_access",
    "create_filesystem_browsing",
    "create_filesystem_explorer",
    "create_filesystem_sharing",
    "create_filesystem_transactions",
    "create_filesystem_creation",
    "create_filesystem_uploads",
    "create_content_driver",
    "create_namespace_driver",
    "create_filesystem",
    "open_portable_draft_validator",
]

_EXPORTS: dict[str, str] = {
    "create_log_archive_backfill": ".telemetry.backfill_composition",
    "create_log_archive_replay": ".telemetry.replay_composition",
    "create_log_archive_replay_with_normalizer": ".telemetry.replay_composition",
    "OutboundHttpClientFactory": ".http",
    "OutboundHttpClientOptions": ".http",
    "open_anonymous_mcp_initialization": ".mcp_endpoint_access",
    "open_official_mcp_registry": ".mcp_registry",
    "create_mcp_metrics": ".metrics.mcp.composition",
    "create_rest_metrics_recorder": ".metrics.rest.composition",
    "create_rest_metrics_http_server": ".metrics.rest.composition",
    "create_telemetry_app": ".metrics.collector.composition",
    "create_receiver_app_with_registry": ".metrics.collector.composition",
    "install_telemetry_receiver": ".metrics.collector.composition",
    "open_portable_draft_validator": ".portable_connectors",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
