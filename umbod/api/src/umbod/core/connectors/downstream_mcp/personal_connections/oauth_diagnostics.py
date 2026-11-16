from typing import Protocol

from .oauth_failure_models import OAuthFailureEvidence


class PersonalOAuthFailureObserver(Protocol):
    def report(self, connector_id: str, evidence: OAuthFailureEvidence) -> None: ...
