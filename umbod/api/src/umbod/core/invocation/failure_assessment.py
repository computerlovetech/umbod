from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

from umbod.core.invocation.diagnostics import InvocationFailureDiagnostic, NoInvocationFailureDiagnostic
from umbod.core.invocation.failure_evidence import (
    InvocationExceptionEvidence,
    InvocationFailureEvidence,
    InvocationFailureOrigin,
    InvocationRejectedFailure,
    InvocationReturnedFailure,
    exception_evidence,
)


class InvocationFailureCategory(StrEnum):
    VALIDATION = "validation"
    AUTHORIZATION = "authorization"
    TOOL_ERROR = "tool_error"
    CONNECTOR_ERROR = "connector_error"


class InvocationRejectionKind(StrEnum):
    NONE = "none"
    VALIDATION = "validation"
    AUTHORIZATION = "authorization"


@dataclass(frozen=True)
class NoInvocationFailureEvidence:
    pass


InvocationDiagnostic: TypeAlias = InvocationFailureDiagnostic | NoInvocationFailureDiagnostic
RecordedInvocationEvidence: TypeAlias = InvocationFailureEvidence | NoInvocationFailureEvidence


@dataclass(frozen=True)
class InvocationFailureAssessment:
    category: InvocationFailureCategory
    diagnostic: InvocationDiagnostic
    evidence: InvocationFailureEvidence


def _diagnostic_rejection(diagnostic: InvocationDiagnostic) -> InvocationRejectionKind:
    if not isinstance(diagnostic, InvocationFailureDiagnostic):
        return InvocationRejectionKind.NONE
    return {
        "invalid_arguments": InvocationRejectionKind.VALIDATION,
        "admission_denied": InvocationRejectionKind.AUTHORIZATION,
        "authorization_rejected": InvocationRejectionKind.AUTHORIZATION,
    }.get(diagnostic.reason, InvocationRejectionKind.NONE)


def _rejected_assessment(rejection: InvocationRejectionKind, diagnostic: InvocationDiagnostic) -> InvocationFailureAssessment:
    category = {
        InvocationRejectionKind.VALIDATION: InvocationFailureCategory.VALIDATION,
        InvocationRejectionKind.AUTHORIZATION: InvocationFailureCategory.AUTHORIZATION,
    }[rejection]
    return InvocationFailureAssessment(category, diagnostic, InvocationRejectedFailure(InvocationFailureOrigin.CLIENT_INPUT))


def assess_raised_invocation_failure(
    error: BaseException,
    *,
    rejection: InvocationRejectionKind,
    diagnostic: InvocationDiagnostic,
    evidence: RecordedInvocationEvidence,
) -> InvocationFailureAssessment:
    diagnostic_rejection = _diagnostic_rejection(diagnostic)
    if diagnostic_rejection != InvocationRejectionKind.NONE:
        return _rejected_assessment(diagnostic_rejection, diagnostic)
    if rejection != InvocationRejectionKind.NONE and not isinstance(evidence, InvocationExceptionEvidence) and not isinstance(diagnostic, InvocationFailureDiagnostic):
        return _rejected_assessment(rejection, diagnostic)
    captured_evidence = exception_evidence(error, InvocationFailureOrigin.INTERNAL) if isinstance(evidence, NoInvocationFailureEvidence) else evidence
    return InvocationFailureAssessment(InvocationFailureCategory.CONNECTOR_ERROR, diagnostic, captured_evidence)


def assess_returned_invocation_failure(
    connector_kind: str,
    *,
    diagnostic: InvocationDiagnostic,
    evidence: RecordedInvocationEvidence,
) -> InvocationFailureAssessment:
    diagnostic_rejection = _diagnostic_rejection(diagnostic)
    if diagnostic_rejection != InvocationRejectionKind.NONE:
        return _rejected_assessment(diagnostic_rejection, diagnostic)
    if isinstance(evidence, NoInvocationFailureEvidence):
        origin = {
            "native": InvocationFailureOrigin.CONNECTOR,
            "downstream_mcp": InvocationFailureOrigin.MCP,
            "openapi": InvocationFailureOrigin.OPENAPI,
        }.get(connector_kind, InvocationFailureOrigin.INTERNAL)
        evidence = InvocationReturnedFailure(origin)
    category = InvocationFailureCategory.TOOL_ERROR
    if isinstance(evidence, InvocationExceptionEvidence) or (isinstance(diagnostic, InvocationFailureDiagnostic) and diagnostic.reason != "downstream_tool_error"):
        category = InvocationFailureCategory.CONNECTOR_ERROR
    return InvocationFailureAssessment(category, diagnostic, evidence)
