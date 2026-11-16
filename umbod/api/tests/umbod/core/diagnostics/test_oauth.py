import json
import logging
from hashlib import sha256

import pytest
from pydantic import ValidationError

from tests.support.application_failures import CapturingApplicationFailures
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_failure_models import OAuthFailureEvidence, OAuthFailureReason
from umbod.core.diagnostics import ApplicationFailure, ApplicationFailureKind, CorrelatedFailureContext, NoFailureContext
from umbod.core.diagnostics.oauth import PublishingOAuthFailureObserver
from umbod.core.invocation.diagnostics import DownstreamHttpResponse, DownstreamResponseEvidence, NoDownstreamResponse
from umbod.logging import OpenTelemetryJsonFormatter, create_application_failure_signal


@pytest.mark.parametrize("response", [NoDownstreamResponse(), DownstreamHttpResponse(status_code=403)])
def test_observer_publishes_immutable_sanitized_evidence(response: DownstreamResponseEvidence) -> None:
    captured = CapturingApplicationFailures()
    observer = PublishingOAuthFailureObserver(captured, CorrelatedFailureContext("a" * 32, None), operation="authorize")
    evidence = OAuthFailureEvidence(stage="registration", reason="provider_rejected", downstream_response=response)

    observer.report("private-connector", evidence)

    assert len(captured.events) == 1
    event = captured.events[0]
    assert event.kind is ApplicationFailureKind.PERSONAL_OAUTH
    assert event.correlation == CorrelatedFailureContext("a" * 32, None)
    attributes = dict(event.attributes)
    assert attributes["connector.id_hash"] == sha256(b"private-connector").hexdigest()
    assert attributes["oauth.stage"] == "registration"
    assert attributes["oauth.reason"] == "provider_rejected"
    assert attributes["oauth.downstream.response_received"] is isinstance(response, DownstreamHttpResponse)
    if isinstance(response, DownstreamHttpResponse):
        assert attributes["oauth.downstream.http.status_code"] == 403
    else:
        assert "oauth.downstream.http.status_code" not in attributes
    assert "private-connector" not in event.model_dump_json()
    with pytest.raises(ValidationError, match="frozen"):
        event.kind = ApplicationFailureKind.AUDIT_SINK
    with pytest.raises(TypeError):
        event.attributes[0] = ("reason", "changed")


@pytest.mark.parametrize("reason,level", [("provider_rejected", logging.WARNING), ("timeout", logging.WARNING), ("invalid_response", logging.WARNING), ("network_failure", logging.WARNING), ("unexpected_failure", logging.ERROR)])
def test_logging_distinguishes_expected_provider_failures_from_alertable_errors(
    caplog: pytest.LogCaptureFixture, reason: OAuthFailureReason, level: int,
) -> None:
    caplog.set_level(logging.WARNING)
    observer = PublishingOAuthFailureObserver(create_application_failure_signal(), NoFailureContext(), operation="authorize")

    observer.report("private-connector", OAuthFailureEvidence(stage="refresh", reason=reason, downstream_response=NoDownstreamResponse()))

    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == level
    payload = json.loads(OpenTelemetryJsonFormatter("test").format(caplog.records[0]))
    assert payload["attributes"]["oauth.reason"] == reason
    assert payload["severity_text"] == ("WARNING" if level == logging.WARNING else "ERROR")
    assert "private-connector" not in json.dumps(payload)


def test_receiver_failure_is_isolated_and_other_application_channels_are_independent(caplog: pytest.LogCaptureFixture) -> None:
    first = create_application_failure_signal()
    second = create_application_failure_signal()
    observed = CapturingApplicationFailures()
    other_application = CapturingApplicationFailures()
    attempted: list[ApplicationFailure] = []

    def fail(event: ApplicationFailure) -> None:
        attempted.append(event)
        raise RuntimeError("private-provider-token")

    first.connect("failing-observer", fail)
    first.connect("capture", observed.send)
    second.connect("capture", other_application.send)
    observer = PublishingOAuthFailureObserver(first, NoFailureContext(), operation="authorize")

    observer.report("private-connector", OAuthFailureEvidence(stage="discovery", reason="timeout", downstream_response=NoDownstreamResponse()))

    assert len(observed.events) == 1
    assert attempted == observed.events
    assert other_application.events == []
    assert "private-provider-token" not in caplog.text
    assert len(caplog.records) == 2


def test_observer_sanitizes_untrusted_correlation_before_publication() -> None:
    captured = CapturingApplicationFailures()
    observer = PublishingOAuthFailureObserver(captured, CorrelatedFailureContext("https://private.example", "private-token"), operation="authorize")

    observer.report("connector", OAuthFailureEvidence(stage="discovery", reason="timeout", downstream_response=NoDownstreamResponse()))

    assert captured.events[0].correlation == CorrelatedFailureContext("[omitted]", "[omitted]")
    assert "private" not in captured.events[0].model_dump_json()
