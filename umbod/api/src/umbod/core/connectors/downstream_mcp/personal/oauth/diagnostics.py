from typing import Protocol

from .failures import OAuthFailureEvidence


class PersonalOAuthFailureObserver(Protocol):
    def report(self, connector_id: str, evidence: OAuthFailureEvidence) -> None: ...
