import httpcore

from contextlib import contextmanager
from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from .transport import OAuthHttpRequest, OAuthHttpResponse, OAuthHttpTransport

from ...personal.oauth.failures import OAuthEvidenceError, OAuthFailureEvidence, OAuthFailureStage, oauth_failure_evidence
from ...personal.oauth.authorization import PersonalOAuthProviderFailure, PersonalOAuthProviderUnsupported
from umbod.core.invocation.diagnostics import DownstreamHttpResponse, DownstreamResponseEvidence, NoDownstreamResponse


class OAuthOperationProgress:
    def __init__(self, stage: OAuthFailureStage) -> None:
        self.begin(stage)

    def begin(self, stage: OAuthFailureStage) -> None:
        self.stage = stage
        self.evidence = OAuthFailureEvidence(
            stage=stage, reason="timeout", downstream_response=NoDownstreamResponse(),
        )

    def failure_evidence(self, error: Exception) -> OAuthFailureEvidence:
        return self.evidence if isinstance(error, TimeoutError) else oauth_failure_evidence(error, self.stage)


@runtime_checkable
class ProgressOAuthHttpTransport(Protocol):
    async def request_with_progress(self, command: OAuthHttpRequest, progress: OAuthOperationProgress) -> OAuthHttpResponse: ...


async def request_with_progress(
    transport: OAuthHttpTransport, command: OAuthHttpRequest, progress: OAuthOperationProgress, stage: OAuthFailureStage,
) -> OAuthHttpResponse:
    progress.begin(stage)
    if isinstance(transport, ProgressOAuthHttpTransport):
        return await transport.request_with_progress(command, progress)
    return await transport.request(command)


def adapter_failure_evidence(error: Exception, stage: OAuthFailureStage) -> OAuthFailureEvidence:
    evidence = oauth_failure_evidence(error, stage)
    if isinstance(error, OAuthEvidenceError):
        return evidence
    current: BaseException | None = error
    primary: BaseException = error
    visited: set[int] = set()
    for _ in range(8):
        if not isinstance(current, Exception) or id(current) in visited:
            break
        visited.add(id(current))
        if isinstance(current, OAuthEvidenceError):
            return current.evidence
        primary = current
        current = current.__cause__ or current.__context__
    evidence = oauth_failure_evidence(primary, stage)
    if isinstance(primary, httpcore.TimeoutException):
        return evidence.model_copy(update={"reason": "timeout"})
    if isinstance(primary, httpcore.NetworkError):
        return evidence.model_copy(update={"reason": "network_failure"})
    return evidence


class OAuthTransportFailure(PersonalOAuthProviderFailure):
    def __init__(self, evidence: OAuthFailureEvidence) -> None:
        super().__init__(evidence)


@contextmanager
def oauth_failure_boundary(stage: OAuthFailureStage, response: DownstreamResponseEvidence) -> Iterator[None]:
    try:
        yield
    except Exception as error:
        evidence = adapter_failure_evidence(error, stage)
        if isinstance(error, OAuthTransportFailure):
            evidence = evidence.model_copy(update={"stage": stage})
        elif isinstance(error, OAuthEvidenceError):
            if isinstance(error, PersonalOAuthProviderUnsupported) and isinstance(evidence.downstream_response, NoDownstreamResponse):
                raise type(error)(evidence.model_copy(update={"downstream_response": response})) from None
            raise
        else:
            evidence = evidence.model_copy(update={
                "downstream_response": response,
                "reason": "invalid_response" if isinstance(error, (ValueError, OverflowError)) else evidence.reason,
            })
        if stage in ("discovery", "registration") and evidence.reason == "invalid_response":
            raise PersonalOAuthProviderUnsupported(evidence) from None
        raise PersonalOAuthProviderFailure(evidence) from None


def rejected_response(stage: OAuthFailureStage, status: int) -> PersonalOAuthProviderFailure:
    return PersonalOAuthProviderFailure(OAuthFailureEvidence(
        stage=stage, reason="provider_rejected", downstream_response=DownstreamHttpResponse(status_code=status),
    ))
