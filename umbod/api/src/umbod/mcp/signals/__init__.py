from umbod.mcp.signals.channels import McpSignals
from umbod.mcp.signals.context import McpInvocationContext, current_mcp_invocation_context, set_mcp_invocation_context
from umbod.mcp.signals.events import (
    McpInteractionType,
    McpInvocationActor,
    McpInvocationCorrelation,
    McpToolIdentity,
    McpToolInvocationCompleted,
    McpToolInvocationEvent,
    McpToolInvocationFailed,
    McpToolInvocationFailureCategory,
    McpToolInvocationOutcome,
    McpToolInvocationStarted,
    McpToolInvocationSucceeded,
    ToolInventoryObserved,
)
from importlib import import_module
from typing import Any

__all__ = [
    "McpSignals", "McpInvocationPublisher", "McpInvocationContext",
    "McpToolExecutionPipelineFactory", "SignalToolExecutionPipelineFactory", "ConnectorInvocationSignalInterceptor",
    "current_mcp_invocation_context", "set_mcp_invocation_context",
    "McpInteractionType", "McpInvocationActor", "McpInvocationCorrelation",
    "McpToolIdentity", "McpToolInvocationCompleted", "McpToolInvocationEvent",
    "McpToolInvocationFailed", "McpToolInvocationFailureCategory",
    "McpToolInvocationOutcome", "McpToolInvocationStarted", "McpToolInvocationSucceeded",
    "ToolInventoryObserved",
]


def __getattr__(name: str) -> Any:
    modules = {
        "McpInvocationPublisher": ".publisher",
        "McpToolExecutionPipelineFactory": ".execution",
        "SignalToolExecutionPipelineFactory": ".execution",
        "ConnectorInvocationSignalInterceptor": ".execution",
    }
    if name not in modules:
        raise AttributeError(name)
    return getattr(import_module(modules[name], __name__), name)
