from typing import Literal

from umbod.core.connectors.downstream_mcp.personal.oauth.failures import OAuthFailureEvidence
from umbod.core.invocation.diagnostics import DownstreamHttpResponse
from umbod.core.signals import SignalPublisher

from .capture import _identifier_fingerprint, _safe_correlation_id
from .models import ApplicationFailure, ApplicationFailureKind, CorrelatedFailureContext, FailureAttribute, NoFailureContext


class PublishingOAuthFailureObserver:
    def __init__(
        self, publisher: SignalPublisher[ApplicationFailure],
        correlation: CorrelatedFailureContext | NoFailureContext,
        operation: Literal["authorize", "validate_setup"],
    ) -> None:
        self._publisher = publisher
        self._operation = operation
        self._correlation = (
            CorrelatedFailureContext(
                _safe_correlation_id(correlation.trace_id, 32),
                _safe_correlation_id(correlation.span_id, 16) if correlation.span_id is not None else None,
            ) if isinstance(correlation, CorrelatedFailureContext) else NoFailureContext()
        )

    def report(self, connector_id: str, evidence: OAuthFailureEvidence) -> None:
        response = evidence.downstream_response
        attributes: dict[FailureAttribute, str | int | bool] = {
            "event.name": "application.failure",
            "component": "personal_oauth",
            "operation": self._operation,
            "reason": evidence.reason,
            "outcome": "failure",
            "failure.origin": "internal" if evidence.reason == "unexpected_failure" else "downstream_mcp",
            "connector.id_hash": _identifier_fingerprint(connector_id),
            "oauth.stage": evidence.stage,
            "oauth.reason": evidence.reason,
            "oauth.downstream.response_received": isinstance(response, DownstreamHttpResponse),
        }
        if isinstance(response, DownstreamHttpResponse):
            attributes["oauth.downstream.http.status_code"] = response.status_code
        self._publisher.send(ApplicationFailure(
            kind=ApplicationFailureKind.PERSONAL_OAUTH,
            attributes=tuple(attributes.items()), correlation=self._correlation,
        ))
