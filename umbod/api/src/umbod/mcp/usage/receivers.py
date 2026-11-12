import math
from re import fullmatch
from uuid import uuid4

from umbod.core.usage.models import UsageKind, UsageOutcome, UsageOwner, UsageRecord
from umbod.mcp.signals.capabilities import McpCapabilityCompleted, McpCapabilityMethod
from umbod.mcp.signals.events import McpInvocationActor, McpInvocationCorrelation, McpToolInvocationCompleted

from .ports import NanosecondClock, NoUsageCorrelation, UsageAdmission


_WRAPPERS = frozenset({'search_tools', 'execute_tool', 'execute_code'})
_CAPABILITY_KINDS = {
    McpCapabilityMethod.READ_RESOURCE: UsageKind.RESOURCE,
    McpCapabilityMethod.GET_PROMPT: UsageKind.PROMPT,
}


class UsageCompletionProjection:
    def __init__(self, admission: UsageAdmission, service_name: str, clock: NanosecondClock) -> None:
        self._admission = admission
        self._service_name = service_name
        self._clock = clock

    def completed(
        self, actor: McpInvocationActor, started_at: int, duration_ms: float,
        correlation: McpInvocationCorrelation | NoUsageCorrelation, kind: UsageKind, outcome: str,
    ) -> None:
        owner = actor.usage_owner
        if not isinstance(owner, UsageOwner):
            return
        try:
            if not math.isfinite(duration_ms):
                raise ValueError('Invalid usage duration')
            duration = max(0.0, duration_ms)
            trace = _correlation_id(correlation.trace_id, 32) if isinstance(correlation, McpInvocationCorrelation) else ''
            span = _correlation_id(correlation.span_id or '', 16) if isinstance(correlation, McpInvocationCorrelation) and trace else ''
            record = UsageRecord(
                event_id=uuid4(), owner_id=owner.owner_id,
                occurred_at_unix_nano=started_at + int(duration * 1_000_000),
                observed_at_unix_nano=self._clock(), kind=kind, outcome=UsageOutcome(outcome),
                duration_ms=duration, service_name=self._service_name, trace_id=trace, span_id=span,
            )
            self._admission.enqueue(record)
        except Exception:
            self._admission.projection_failed()


class InvocationUsageReceiver:
    def __init__(self, projection: UsageCompletionProjection) -> None:
        self._projection = projection

    def __call__(self, event: McpToolInvocationCompleted) -> None:
        started = event.started
        if started.tool.connector_id is None and started.tool.tool_name in _WRAPPERS:
            return
        self._projection.completed(
            started.actor, started.started_at_unix_nano, event.duration_ms,
            started.correlation if started.correlation is not None else NoUsageCorrelation(),
            UsageKind.TOOL, event.outcome.value,
        )


class CapabilityUsageReceiver:
    def __init__(self, projection: UsageCompletionProjection) -> None:
        self._projection = projection

    def __call__(self, event: McpCapabilityCompleted) -> None:
        kind = _CAPABILITY_KINDS.get(event.method)
        if kind is None:
            return
        self._projection.completed(
            event.actor, event.started_at_unix_nano, event.duration_ms,
            event.correlation, kind, event.outcome.value,
        )


def _correlation_id(value: str, length: int) -> str:
    if isinstance(value, str) and fullmatch(f'[0-9a-f]{{{length}}}', value) and int(value, 16):
        return value
    return ''
