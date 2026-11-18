from typing import Protocol

from umbod.core.invocation.diagnostics import InvocationFailureDiagnostic, NoInvocationFailureDiagnostic
from umbod.core.invocation.failure_evidence import InvocationFailureEvidence
from umbod.mcp.signals.events import McpToolIdentity, McpToolInvocationFailureCategory
from umbod.mcp.signals.lifecycle import McpToolInvocationLifecycle, UnavailableToolInvocationLifecycle


class McpInvocationPublishing(Protocol):
    def start(self, identity: McpToolIdentity) -> McpToolInvocationLifecycle | UnavailableToolInvocationLifecycle: ...

    def succeeded(self, lifecycle: McpToolInvocationLifecycle | UnavailableToolInvocationLifecycle) -> None: ...

    def failed(self, lifecycle: McpToolInvocationLifecycle | UnavailableToolInvocationLifecycle, category: McpToolInvocationFailureCategory, diagnostic: InvocationFailureDiagnostic | NoInvocationFailureDiagnostic, evidence: InvocationFailureEvidence) -> None: ...

    def report_failure(self, name: str, error: Exception) -> None: ...
