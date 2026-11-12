from hashlib import sha256
from re import fullmatch

from umbod.core.invocation.failure_evidence import InvocationFailureOrigin, exception_evidence
from umbod.core.signals import SignalPublisher

from .models import (
    ApplicationFailure, ApplicationFailureKind, ConnectorLookupFailureContext,
    CorrelatedFailureContext, FailureAttribute, FailureContext, NoFailureContext,
    RestFailureContext, SignalFailureContext,
)


def _bounded_stacktrace(stacktrace: str) -> str:
    if len(stacktrace) <= 4096:
        return stacktrace
    return stacktrace[:4064] + "\n[stacktrace truncated]"


def _identifier_fingerprint(value: str) -> str:
    if type(value) is not str or len(value) > 4096:
        return "[omitted]"
    return sha256(value.encode("utf-8", errors="replace")).hexdigest()


def capture_application_failure(
    event: ApplicationFailureKind,
    error: BaseException,
    context: FailureContext,
) -> ApplicationFailure:
    _, component, operation, reason = event.value
    evidence = exception_evidence(error, InvocationFailureOrigin.INTERNAL)
    attributes: dict[FailureAttribute, str | int] = {
        "event.name": "application.failure",
        "component": component,
        "operation": operation,
        "reason": reason,
        "outcome": "failure",
        "failure.origin": evidence.origin.value,
        "exception.type": evidence.exception_type if len(evidence.exception_type) <= 4096 else "[omitted]",
        "exception.stacktrace": _bounded_stacktrace(evidence.stacktrace),
    }
    if event is ApplicationFailureKind.REST_METRICS and isinstance(context, RestFailureContext):
        attributes["method"] = context.method if context.method in {
            "DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"
        } else "OTHER"
        attributes["status_code"] = context.status_code if 100 <= context.status_code <= 599 else 0
        route = context.normalized_route
        attributes["normalized_route"] = (
            route if type(route) is str and route.startswith("/admin/")
            and len(route) <= 512 and not any(marker in route for marker in ("?", "#", "://"))
            else "unmatched"
        )
    if event is ApplicationFailureKind.CONNECTOR_LOOKUP and isinstance(context, ConnectorLookupFailureContext):
        attributes["connector.id_hash"] = _identifier_fingerprint(context.connector_id)
        attributes["operation.name_hash"] = _identifier_fingerprint(context.operation_name)
    if event is ApplicationFailureKind.SIGNAL_RECEIVER and isinstance(context, SignalFailureContext):
        known_receivers = {
            "mcp.invocation.logging", "mcp.invocation.metrics",
            "mcp.invocation.audit", "mcp.inventory.metrics", "mcp.capability.logging",
            "mcp.invocation.usage", "mcp.capability.usage",
            "application.failure.logging",
        }
        if context.receiver_name in known_receivers:
            attributes["receiver.name"] = context.receiver_name
        else:
            attributes["receiver.name"] = "unrecognized"
            attributes["receiver.name_hash"] = _identifier_fingerprint(context.receiver_name)
    correlation = (
        CorrelatedFailureContext(
            _safe_correlation_id(context.trace_id, 32),
            _safe_correlation_id(context.span_id, 16) if context.span_id is not None else None,
        )
        if isinstance(context, CorrelatedFailureContext) else NoFailureContext()
    )
    return ApplicationFailure(kind=event, attributes=tuple(attributes.items()), correlation=correlation)


def _safe_correlation_id(value: str, length: int) -> str:
    if type(value) is str and fullmatch(f"[0-9a-f]{{{length}}}", value):
        return value
    return "[omitted]"


class PublishingSignalFailureHandler:
    def __init__(self, application_failures: SignalPublisher[ApplicationFailure]) -> None:
        self._application_failures = application_failures

    def handles(self, receiver_name: str, error: Exception) -> None:
        report_application_failure(
            self._application_failures, ApplicationFailureKind.SIGNAL_RECEIVER,
            error, SignalFailureContext(receiver_name),
        )


def report_application_failure(
    publisher: SignalPublisher[ApplicationFailure],
    kind: ApplicationFailureKind,
    error: BaseException,
    context: FailureContext,
) -> None:
    publisher.send(capture_application_failure(kind, error, context))
