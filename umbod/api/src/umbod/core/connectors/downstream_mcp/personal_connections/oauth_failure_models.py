from typing import Literal

from pydantic import BaseModel, ConfigDict

from umbod.core.invocation.diagnostics import DownstreamResponseEvidence, NoDownstreamResponse


OAuthFailureStage = Literal["discovery", "registration", "token_exchange", "refresh"]
OAuthFailureReason = Literal["provider_rejected", "timeout", "invalid_response", "network_failure", "unexpected_failure"]


class OAuthFailureEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: OAuthFailureStage
    reason: OAuthFailureReason
    downstream_response: DownstreamResponseEvidence


class OAuthEvidenceError(ValueError):
    stage: OAuthFailureStage = "discovery"
    reason: OAuthFailureReason = "unexpected_failure"
    message: str = "Personal OAuth provider request failed"

    def __init__(self, *arguments: OAuthFailureEvidence | str, **keywords: OAuthFailureEvidence) -> None:
        if len(arguments) > 1 or set(keywords) - {"evidence"} or (arguments and keywords):
            raise TypeError("Invalid OAuth failure arguments")
        provided = arguments[0] if arguments else keywords.get("evidence")
        self.evidence = provided if isinstance(provided, OAuthFailureEvidence) else OAuthFailureEvidence(
            stage=self.stage, reason=self.reason, downstream_response=NoDownstreamResponse(),
        )
        super().__init__(self.message)


def oauth_failure_evidence(error: BaseException, stage: OAuthFailureStage) -> OAuthFailureEvidence:
    if isinstance(error, OAuthEvidenceError):
        return error.evidence
    return OAuthFailureEvidence(
        stage=stage, reason=(
            "timeout" if isinstance(error, TimeoutError) else
            "network_failure" if isinstance(error, OSError) else "unexpected_failure"
        ),
        downstream_response=NoDownstreamResponse(),
    )
