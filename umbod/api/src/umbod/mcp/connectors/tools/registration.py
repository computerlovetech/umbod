from collections.abc import Mapping, Sequence
from typing import cast

from fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, SkipValidation
from umbod.mcp.proxies import Model
from umbod.proxies import Model as ConnectorConfigurationModel

from umbod.core.configuration import ConnectorCurrentConfigurationStore
from umbod.core.invocation import ConnectorInvocationPolicy
from umbod.core.capabilities.descriptions import (
    ConnectorCapabilityDescriptionOverrideStore,
    SystemConnectorCapabilityDescriptionOverrideStore,
)
from umbod.core.publishing import (
    ConnectorPublishStateChangeSource,
    ConnectorPublishingStore,
)
from umbod.core.connectors.native.runtime.tools import ConnectorToolMapping
from umbod.core.capabilities.tools.names import PublicToolIdentity, validate_unique_public_tool_names

from umbod.mcp.connectors.tools.file_input import (
    DEFAULT_MAXIMUM_UPLOADED_FILE_BYTES,
    uploaded_file_parameter_name,
)
from umbod.mcp.connectors.tools.infrastructure.client_notifications import (
    install_tool_list_changed_notifier,
)
from umbod.mcp.connectors.tools.deployment_modes import ConnectorToolExposureMode
from umbod.mcp.connectors.tools.deployment_modes.resolver import (
    connector_tool_deployment_factory,
)
from umbod.core.connectors.native.capabilities import ConnectorToolRuntimeStateReader
from umbod.mcp.connectors.tools.invocation.errors import ConnectorToolErrorFormatter
from umbod.mcp.connectors.tools.runtime.registry import (
    ConnectorToolInvokerDependencies,
    RuntimeConnectorToolRegistry,
    _server_name,
    create_connector_tool_invoker_factory,
)
from umbod.mcp.metrics import McpMetricsRecorder, PrometheusMcpMetricsRecorder
from umbod.mcp.logging import (
    McpAuditRecorder,
    McpToolInvocationLogSink,
    create_default_mcp_audit_recorder,
)


class ConnectorToolRegistrationOptions(Model):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
    )

    connector_registrations: Sequence[Mapping[str, object]] | None
    connector_configuration_store: SkipValidation[ConnectorCurrentConfigurationStore | None]
    connector_publishing_store: SkipValidation[ConnectorPublishingStore | None]
    connector_tool_mappings: SkipValidation[Sequence[ConnectorToolMapping] | None]
    capability_description_overrides: SkipValidation[ConnectorCapabilityDescriptionOverrideStore] = Field(
        default_factory=SystemConnectorCapabilityDescriptionOverrideStore
    )
    error_formatter: ConnectorToolErrorFormatter | None
    connector_tool_runtime_state_store: SkipValidation[ConnectorToolRuntimeStateReader | None]
    tool_invocation_log_sink: SkipValidation[McpToolInvocationLogSink]
    audit_recorder: SkipValidation[McpAuditRecorder | None] = None
    metrics_recorder: SkipValidation[McpMetricsRecorder] = Field(
        default_factory=PrometheusMcpMetricsRecorder
    )
    connector_tool_exposure_mode: ConnectorToolExposureMode = "flat"
    connector_code_execution_timeout_seconds: float = 30.0
    maximum_uploaded_file_bytes: int = Field(
        default=DEFAULT_MAXIMUM_UPLOADED_FILE_BYTES,
        gt=0,
    )
    invocation_policy: SkipValidation[ConnectorInvocationPolicy]


async def register_connector_tools(
    mcp: FastMCP,
    *option_arguments: ConnectorToolRegistrationOptions | None,
    **registration_options: object,
) -> None:
    resolved_options = _resolve_registration_options(option_arguments, registration_options)
    if not _has_required_registration_options(resolved_options):
        return
    if resolved_options.tool_invocation_log_sink is None:
        raise TypeError(
            "register_connector_tools() missing required argument: 'tool_invocation_log_sink'"
        )
    connector_tool_mappings = cast(
        Sequence[ConnectorToolMapping], resolved_options.connector_tool_mappings
    )
    if resolved_options.connector_tool_exposure_mode != "flat" and any(
        uploaded_file_parameter_name(mapping.operation) is not None
        for mapping in connector_tool_mappings
    ):
        raise ValueError("UploadedFile connector tools are supported only in flat exposure mode")
    error_formatter = resolved_options.error_formatter or ConnectorToolErrorFormatter()
    audit_recorder = resolved_options.audit_recorder or create_default_mcp_audit_recorder(
        _server_name(mcp)
    )
    client_notifier = install_tool_list_changed_notifier(mcp)
    deployment_factory = connector_tool_deployment_factory(
        resolved_options.connector_tool_exposure_mode,
        resolved_options.connector_code_execution_timeout_seconds,
        resolved_options.maximum_uploaded_file_bytes,
    )
    exposure_strategy = deployment_factory.create_exposure_strategy(
        mcp,
        create_connector_tool_invoker_factory(
            ConnectorToolInvokerDependencies(
                error_formatter=error_formatter,
                tool_invocation_log_sink=resolved_options.tool_invocation_log_sink,
                audit_recorder=audit_recorder,
                metrics_recorder=resolved_options.metrics_recorder,
                connector_display_names=_connector_display_names(
                    cast(Sequence[Mapping[str, object]], resolved_options.connector_registrations)
                ),
                invocation_policy=resolved_options.invocation_policy,
            )
        ),
        client_notifier,
    )
    validate_unique_public_tool_names(
        tuple(
            PublicToolIdentity(
                connector_id=mapping.connector_id,
                tool_name_prefix=getattr(mapping, "tool_name_prefix", "")
                or mapping.connector_id,
                operation_name=mapping.operation_name,
            )
            for mapping in connector_tool_mappings
        )
    )
    registry = RuntimeConnectorToolRegistry(
        mcp,
        schemas=_valid_configuration_schemas(
            cast(Sequence[Mapping[str, object]], resolved_options.connector_registrations)
        ),
        connector_display_names=_connector_display_names(
            cast(Sequence[Mapping[str, object]], resolved_options.connector_registrations)
        ),
        connector_capability_descriptions=_connector_capability_descriptions(
            cast(Sequence[Mapping[str, object]], resolved_options.connector_registrations)
        ),
        connector_configuration_store=cast(
            ConnectorCurrentConfigurationStore, resolved_options.connector_configuration_store
        ),
        connector_publishing_store=cast(
            ConnectorPublishingStore, resolved_options.connector_publishing_store
        ),
        connector_tool_mappings=connector_tool_mappings,
        capability_description_overrides=cast(
            ConnectorCapabilityDescriptionOverrideStore, resolved_options.capability_description_overrides
        ),
        error_formatter=error_formatter,
        connector_tool_runtime_state_store=resolved_options.connector_tool_runtime_state_store,
        tool_invocation_log_sink=resolved_options.tool_invocation_log_sink,
        audit_recorder=audit_recorder,
        client_notifier=client_notifier,
        exposure_strategy=exposure_strategy,
        metrics_recorder=resolved_options.metrics_recorder,
        invocation_policy=resolved_options.invocation_policy,
    )
    setattr(mcp, "connector_tool_registry", registry)
    deployment_factory.register_fixed_tools(mcp, registry)
    await registry.reconcile_all()
    connector_publishing_store = resolved_options.connector_publishing_store
    if isinstance(connector_publishing_store, ConnectorPublishStateChangeSource):
        connector_publishing_store.subscribe_publish_state_changes(
            registry.handle_publish_state_changed
        )


def _resolve_registration_options(
    option_arguments: Sequence[ConnectorToolRegistrationOptions | None],
    registration_options: Mapping[str, object],
) -> ConnectorToolRegistrationOptions:
    if len(option_arguments) > 1:
        raise TypeError("register_connector_tools() takes from 1 to 2 positional arguments")
    if option_arguments and "options" in registration_options:
        raise TypeError("register_connector_tools() got multiple values for argument 'options'")
    options = _explicit_registration_options(option_arguments, registration_options)
    legacy_options = _legacy_registration_options(registration_options)
    if options is not None and legacy_options:
        unknown_option = next(iter(legacy_options))
        raise TypeError(
            f"register_connector_tools() got an unexpected keyword argument '{unknown_option}'"
        )
    if options is not None:
        return options
    return ConnectorToolRegistrationOptions.model_validate(
        _registration_option_data(legacy_options)
    )


def _explicit_registration_options(
    option_arguments: Sequence[ConnectorToolRegistrationOptions | None],
    registration_options: Mapping[str, object],
) -> ConnectorToolRegistrationOptions | None:
    if option_arguments:
        return option_arguments[0]
    return cast(ConnectorToolRegistrationOptions | None, registration_options.get("options"))


def _legacy_registration_options(
    registration_options: Mapping[str, object],
) -> Mapping[str, object]:
    return {key: value for key, value in registration_options.items() if key != "options"}


def _registration_option_data(legacy_options: Mapping[str, object]) -> dict[str, object]:
    return {
        "connector_registrations": None,
        "connector_configuration_store": None,
        "connector_publishing_store": None,
        "connector_tool_mappings": None,
        "error_formatter": None,
        "connector_tool_runtime_state_store": None,
        "audit_recorder": None,
        "connector_tool_exposure_mode": "flat",
        "connector_code_execution_timeout_seconds": 30.0,
        "maximum_uploaded_file_bytes": DEFAULT_MAXIMUM_UPLOADED_FILE_BYTES,
        **legacy_options,
    }


def _has_required_registration_options(options: ConnectorToolRegistrationOptions) -> bool:
    return bool(
        options.connector_registrations is not None
        and options.connector_configuration_store is not None
        and options.connector_publishing_store is not None
        and options.connector_tool_mappings is not None
    )


def _connector_display_names(
    registrations: Sequence[Mapping[str, object]],
) -> dict[str, str]:
    return {
        connector_id: display_name
        for registration in registrations
        if isinstance((connector_id := registration.get("id")), str)
        and isinstance((display_name := registration.get("display_name")), str)
        and display_name
    }


def _connector_capability_descriptions(
    registrations: Sequence[Mapping[str, object]],
) -> dict[str, str]:
    return {
        connector_id: capability_description
        for registration in registrations
        if isinstance((connector_id := registration.get("id")), str)
        and isinstance(
            (capability_description := registration.get("capability_description")), str
        )
        and capability_description
    }


def _valid_configuration_schemas(
    registrations: Sequence[Mapping[str, object]],
) -> dict[str, type[ConnectorConfigurationModel]]:
    schemas: dict[str, type[ConnectorConfigurationModel]] = {}
    for registration in registrations:
        connector_id = registration.get("id")
        configuration_schema = registration.get("configuration_schema")
        if (
            isinstance(connector_id, str)
            and isinstance(configuration_schema, type)
            and issubclass(configuration_schema, BaseModel)
        ):
            schemas[connector_id] = configuration_schema
    return schemas
