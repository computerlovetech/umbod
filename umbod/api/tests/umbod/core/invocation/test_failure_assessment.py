from dataclasses import FrozenInstanceError

import pytest

from umbod.core.invocation.diagnostics import (
    DownstreamHttpResponse,
    InvocationFailureDiagnostic,
    NoInvocationFailureDiagnostic,
)
from umbod.core.invocation import (
    InvocationFailureAssessment,
    InvocationFailureCategory,
    InvocationRejectionKind,
    NoInvocationFailureEvidence,
    RecordedInvocationEvidence,
    assess_raised_invocation_failure,
    assess_returned_invocation_failure,
)
from umbod.core.invocation.failure_evidence import (
    InvocationExceptionEvidence,
    InvocationFailureOrigin,
    InvocationRejectedFailure,
    InvocationReturnedFailure,
    exception_evidence,
)


@pytest.mark.parametrize(
    "diagnostic",
    [
        InvocationFailureDiagnostic(execution_mode="personal", stage="authorization", reason="authorization_health_unavailable"),
        InvocationFailureDiagnostic(execution_mode="personal", stage="context", reason="context_unavailable"),
        InvocationFailureDiagnostic(execution_mode="personal", stage="runtime", reason="runtime_failure"),
        InvocationFailureDiagnostic(execution_mode="personal", stage="output", reason="invalid_output"),
        InvocationFailureDiagnostic(execution_mode="personal", stage="transport", reason="transport_failure"),
        InvocationFailureDiagnostic(execution_mode="personal", stage="transport", reason="contract_mismatch"),
        InvocationFailureDiagnostic(execution_mode="personal", stage="transport", reason="target_expired"),
    ],
)
@pytest.mark.parametrize("preserved_exception", [True, False])
@pytest.mark.parametrize("returned_error", [True, False])
def test_failure_does_not_downgrade_preserved_server_diagnostic(
    diagnostic: InvocationFailureDiagnostic, preserved_exception: bool, returned_error: bool,
) -> None:
    evidence = exception_evidence(RuntimeError("private-underlying"), InvocationFailureOrigin.INTERNAL) if preserved_exception else NoInvocationFailureEvidence()
    assessment = assess_returned_invocation_failure("openapi", diagnostic=diagnostic, evidence=evidence) if returned_error else assess_raised_invocation_failure(
        RuntimeError("private-denial"), rejection=InvocationRejectionKind.AUTHORIZATION, diagnostic=diagnostic, evidence=evidence,
    )

    assert assessment.category == InvocationFailureCategory.CONNECTOR_ERROR
    assert assessment.diagnostic is diagnostic
    if preserved_exception:
        assert assessment.evidence is evidence
    elif returned_error:
        assert assessment.evidence == InvocationReturnedFailure(InvocationFailureOrigin.OPENAPI)
    else:
        assert isinstance(assessment.evidence, InvocationExceptionEvidence)
    assert "private-underlying" not in repr(assessment)
    assert "private-denial" not in repr(assessment)


@pytest.mark.parametrize(
    ("diagnostic", "category"),
    [
        (InvocationFailureDiagnostic(execution_mode="personal", stage="arguments", reason="invalid_arguments"), InvocationFailureCategory.VALIDATION),
        (InvocationFailureDiagnostic(execution_mode="personal", stage="admission", reason="admission_denied"), InvocationFailureCategory.AUTHORIZATION),
        (InvocationFailureDiagnostic(execution_mode="personal", stage="authorization", reason="authorization_rejected"), InvocationFailureCategory.AUTHORIZATION),
    ],
)
@pytest.mark.parametrize("returned_error", [True, False])
@pytest.mark.parametrize("preserved_exception", [True, False])
def test_explicit_rejection_diagnostic_overrides_wrapped_exception(
    diagnostic: InvocationFailureDiagnostic, category: InvocationFailureCategory,
    returned_error: bool, preserved_exception: bool,
) -> None:
    evidence = exception_evidence(RuntimeError("private-rejection"), InvocationFailureOrigin.INTERNAL) if preserved_exception else NoInvocationFailureEvidence()
    assessment = assess_returned_invocation_failure("openapi", diagnostic=diagnostic, evidence=evidence) if returned_error else assess_raised_invocation_failure(
        RuntimeError("private-wrapper"), rejection=InvocationRejectionKind.NONE, diagnostic=diagnostic, evidence=evidence,
    )

    assert assessment.category == category
    assert assessment.diagnostic is diagnostic
    assert assessment.evidence == InvocationRejectedFailure(InvocationFailureOrigin.CLIENT_INPUT)
    assert "private-rejection" not in repr(assessment)
    assert "private-wrapper" not in repr(assessment)


@pytest.mark.parametrize(
    ("rejection", "category"),
    [
        (InvocationRejectionKind.VALIDATION, InvocationFailureCategory.VALIDATION),
        (InvocationRejectionKind.AUTHORIZATION, InvocationFailureCategory.AUTHORIZATION),
    ],
)
@pytest.mark.parametrize(
    "evidence",
    [NoInvocationFailureEvidence(), InvocationReturnedFailure(InvocationFailureOrigin.MCP)],
)
def test_raised_rejection_overrides_absent_or_returned_evidence(
    rejection: InvocationRejectionKind, category: InvocationFailureCategory, evidence: RecordedInvocationEvidence,
) -> None:
    assessment = assess_raised_invocation_failure(
        RuntimeError("private-input"), rejection=rejection, diagnostic=NoInvocationFailureDiagnostic(), evidence=evidence,
    )

    assert assessment.category == category
    assert assessment.evidence == InvocationRejectedFailure(InvocationFailureOrigin.CLIENT_INPUT)
    assert "private-input" not in repr(assessment)


@pytest.mark.parametrize("rejection", list(InvocationRejectionKind))
def test_captured_exception_prevents_raised_rejection(rejection: InvocationRejectionKind) -> None:
    evidence = exception_evidence(RuntimeError("private-source"), InvocationFailureOrigin.MCP)
    assessment = assess_raised_invocation_failure(
        RuntimeError("private-wrapper"), rejection=rejection, diagnostic=NoInvocationFailureDiagnostic(), evidence=evidence,
    )

    assert assessment.category == InvocationFailureCategory.CONNECTOR_ERROR
    assert assessment.evidence is evidence


@pytest.mark.parametrize(
    "evidence",
    [
        InvocationReturnedFailure(InvocationFailureOrigin.CONNECTOR),
        InvocationRejectedFailure(InvocationFailureOrigin.CLIENT_INPUT),
        InvocationExceptionEvidence(InvocationFailureOrigin.MCP, "RuntimeError", "sanitized traceback"),
    ],
)
def test_non_rejection_raised_failure_preserves_recorded_evidence(evidence: RecordedInvocationEvidence) -> None:
    diagnostic = NoInvocationFailureDiagnostic()
    assessment = assess_raised_invocation_failure(
        RuntimeError("private-wrapper"), rejection=InvocationRejectionKind.NONE, diagnostic=diagnostic, evidence=evidence,
    )

    assert assessment.category == InvocationFailureCategory.CONNECTOR_ERROR
    assert assessment.evidence is evidence
    assert assessment.diagnostic is diagnostic


@pytest.mark.parametrize(
    ("connector_kind", "origin"),
    [
        ("native", InvocationFailureOrigin.CONNECTOR),
        ("downstream_mcp", InvocationFailureOrigin.MCP),
        ("openapi", InvocationFailureOrigin.OPENAPI),
        ("unknown", InvocationFailureOrigin.INTERNAL),
        ("", InvocationFailureOrigin.INTERNAL),
    ],
)
def test_returned_failure_falls_back_to_connector_origin(connector_kind: str, origin: InvocationFailureOrigin) -> None:
    diagnostic = NoInvocationFailureDiagnostic()
    assessment = assess_returned_invocation_failure(
        connector_kind, diagnostic=diagnostic, evidence=NoInvocationFailureEvidence(),
    )

    assert assessment.category == InvocationFailureCategory.TOOL_ERROR
    assert assessment.evidence == InvocationReturnedFailure(origin)
    assert assessment.diagnostic is diagnostic


@pytest.mark.parametrize(
    ("evidence", "category"),
    [
        (InvocationReturnedFailure(InvocationFailureOrigin.CONNECTOR), InvocationFailureCategory.TOOL_ERROR),
        (InvocationRejectedFailure(InvocationFailureOrigin.CLIENT_INPUT), InvocationFailureCategory.TOOL_ERROR),
        (InvocationExceptionEvidence(InvocationFailureOrigin.MCP, "RuntimeError", "sanitized traceback"), InvocationFailureCategory.CONNECTOR_ERROR),
    ],
)
def test_returned_failure_preserves_evidence_over_connector_fallback(
    evidence: RecordedInvocationEvidence, category: InvocationFailureCategory,
) -> None:
    assessment = assess_returned_invocation_failure("openapi", diagnostic=NoInvocationFailureDiagnostic(), evidence=evidence)

    assert assessment.category == category
    assert assessment.evidence is evidence


@pytest.mark.parametrize(
    ("diagnostic", "category"),
    [
        (InvocationFailureDiagnostic(execution_mode="shared", stage="downstream", reason="downstream_tool_error"), InvocationFailureCategory.TOOL_ERROR),
        (InvocationFailureDiagnostic(execution_mode="shared", stage="downstream", reason="downstream_exception"), InvocationFailureCategory.CONNECTOR_ERROR),
        (InvocationFailureDiagnostic(execution_mode="shared", stage="transport", reason="http_rejected", downstream_response=DownstreamHttpResponse(status_code=503)), InvocationFailureCategory.CONNECTOR_ERROR),
    ],
)
@pytest.mark.parametrize("preserved_exception", [False, True])
def test_returned_downstream_tool_error_differs_from_backend_diagnostics(
    diagnostic: InvocationFailureDiagnostic, category: InvocationFailureCategory, preserved_exception: bool,
) -> None:
    evidence = exception_evidence(RuntimeError("private-source"), InvocationFailureOrigin.OPENAPI) if preserved_exception else InvocationReturnedFailure(InvocationFailureOrigin.OPENAPI)
    assessment = assess_returned_invocation_failure("native", diagnostic=diagnostic, evidence=evidence)

    assert assessment.category == (InvocationFailureCategory.CONNECTOR_ERROR if preserved_exception else category)
    assert assessment.evidence is evidence
    assert assessment.diagnostic is diagnostic
    assert assessment.diagnostic.downstream_response is diagnostic.downstream_response


@pytest.mark.parametrize("returned_error", [False, True])
def test_assessment_preserves_diagnostic_and_http_response_identity(returned_error: bool) -> None:
    response = DownstreamHttpResponse(status_code=502)
    diagnostic = InvocationFailureDiagnostic(execution_mode="personal", stage="transport", reason="http_rejected", downstream_response=response)
    evidence = InvocationReturnedFailure(InvocationFailureOrigin.OPENAPI)
    assessment = assess_returned_invocation_failure("openapi", diagnostic=diagnostic, evidence=evidence) if returned_error else assess_raised_invocation_failure(
        RuntimeError("private-wrapper"), rejection=InvocationRejectionKind.NONE, diagnostic=diagnostic, evidence=evidence,
    )

    assert assessment.diagnostic is diagnostic
    assert assessment.diagnostic.downstream_response is response
    assert response.status_code == 502
    assert assessment.evidence is evidence


def test_raised_fallback_sanitizes_exception_chain_without_losing_type_or_frames() -> None:
    try:
        try:
            raise ValueError("private-cause")
        except ValueError as cause:
            raise RuntimeError("private-wrapper") from cause
    except RuntimeError as error:
        assessment = assess_raised_invocation_failure(
            error, rejection=InvocationRejectionKind.NONE, diagnostic=NoInvocationFailureDiagnostic(), evidence=NoInvocationFailureEvidence(),
        )

    assert assessment.category == InvocationFailureCategory.CONNECTOR_ERROR
    assert isinstance(assessment.evidence, InvocationExceptionEvidence)
    assert assessment.evidence.origin == InvocationFailureOrigin.INTERNAL
    assert assessment.evidence.exception_type == "RuntimeError"
    assert "ValueError: [message omitted]" in assessment.evidence.stacktrace
    assert "RuntimeError: [message omitted]" in assessment.evidence.stacktrace
    assert "test_raised_fallback_sanitizes_exception_chain" in assessment.evidence.stacktrace
    assert "private-cause" not in repr(assessment)
    assert "private-wrapper" not in repr(assessment)


def test_assessment_is_immutable_and_keeps_explicit_inputs() -> None:
    diagnostic = NoInvocationFailureDiagnostic()
    evidence = InvocationReturnedFailure(InvocationFailureOrigin.MCP)
    assessment = InvocationFailureAssessment(InvocationFailureCategory.TOOL_ERROR, diagnostic, evidence)

    assert assessment.diagnostic is diagnostic
    assert assessment.evidence is evidence
    with pytest.raises(FrozenInstanceError):
        setattr(assessment, "category", InvocationFailureCategory.CONNECTOR_ERROR)


def test_absent_evidence_is_immutable() -> None:
    evidence = NoInvocationFailureEvidence()

    with pytest.raises(FrozenInstanceError):
        setattr(evidence, "origin", InvocationFailureOrigin.INTERNAL)
