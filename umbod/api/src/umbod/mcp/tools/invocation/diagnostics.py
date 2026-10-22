from contextvars import ContextVar

from umbod.core.invocation.diagnostics import InvocationFailureDiagnostic


invocation_failure: ContextVar[InvocationFailureDiagnostic | None] = ContextVar("invocation_failure", default=None)
