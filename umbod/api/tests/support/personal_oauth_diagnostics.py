from umbod.core.connectors.downstream_mcp.personal_connections.oauth_failure_models import OAuthFailureEvidence


class RecordingOAuthFailureObserver:
    def __init__(self) -> None:
        self.failures: list[tuple[str, OAuthFailureEvidence]] = []

    def report(self, connector_id: str, evidence: OAuthFailureEvidence) -> None:
        self.failures.append((connector_id, evidence))
