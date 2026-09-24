from importlib import import_module
from typing import Any

__all__ = [
    "ActivationEventPublicationPolicy",
    "AlwaysPublishActivationEvents",
    "ConnectorToolActivationChange",
    "ConnectorToolConfigurationMutation",
    "ConnectorToolConfigurationMutationPort",
    "ConnectorToolConfigurationMutationResult",
    "ConnectorToolConfigurationSnapshot",
    "ConnectorToolInvocationPolicyChange",
    "ConnectorToolInvocationPolicyMutationResult",
    "DatabaseConnectorToolConfigurationMutationAdapter",
    "InMemoryConnectorToolConfigurationMutationAdapter",
    "NoConnectorToolConfigurationEventStream",
    "OrderedToolExecutionPipeline",
    "PreparedToolExecution",
    "SetConnectorToolActivation",
    "SetConnectorToolConfiguration",
    "SetConnectorToolConfigurationCommand",
    "SetConnectorToolInvocationPolicy",
    "SuppressActivationEvents",
    "ToolExecutionContext",
    "ToolExecutionFailed",
    "ToolExecutionOutcome",
    "ToolExecutionPipeline",
    "ToolExecutionRequest",
    "ToolExecutionSucceeded",
    "create_tool_execution_pipeline",
    "prepare_tool_execution",
]

_EXPORTS: dict[str, str] = {
    "ActivationEventPublicationPolicy": ".configuration",
    "AlwaysPublishActivationEvents": ".configuration",
    "ConnectorToolActivationChange": ".configuration_mutation",
    "ConnectorToolConfigurationMutation": ".configuration_mutation",
    "ConnectorToolConfigurationMutationPort": ".configuration_mutation",
    "ConnectorToolConfigurationMutationResult": ".configuration_mutation",
    "ConnectorToolConfigurationSnapshot": ".configuration_mutation",
    "ConnectorToolInvocationPolicyChange": ".configuration_mutation",
    "ConnectorToolInvocationPolicyMutationResult": ".configuration_mutation",
    "DatabaseConnectorToolConfigurationMutationAdapter": ".database_configuration_mutation",
    "InMemoryConnectorToolConfigurationMutationAdapter": ".configuration_mutation",
    "NoConnectorToolConfigurationEventStream": ".configuration",
    "OrderedToolExecutionPipeline": ".execution",
    "PreparedToolExecution": ".execution",
    "SetConnectorToolActivation": ".configuration",
    "SetConnectorToolConfiguration": ".configuration",
    "SetConnectorToolConfigurationCommand": ".configuration",
    "SetConnectorToolInvocationPolicy": ".configuration",
    "SuppressActivationEvents": ".configuration",
    "ToolExecutionContext": ".execution",
    "ToolExecutionFailed": ".execution",
    "ToolExecutionOutcome": ".execution",
    "ToolExecutionPipeline": ".execution",
    "ToolExecutionRequest": ".execution",
    "ToolExecutionSucceeded": ".execution",
    "create_tool_execution_pipeline": ".execution",
    "prepare_tool_execution": ".execution",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
