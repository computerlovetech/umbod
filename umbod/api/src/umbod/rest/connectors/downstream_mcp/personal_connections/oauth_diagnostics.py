import logging

from umbod.core.connectors.downstream_mcp.personal_connections.oauth_diagnostics import (
    PersonalOAuthScopeMismatchObserved,
)
from umbod.core.diagnostics import PublishingSignalFailureHandler
from umbod.core.signals import Signal
from umbod.logging import create_application_failure_signal


SCOPE_MISMATCH_LOGGING_RECEIVER = "personal_oauth.scope_mismatch.logging"


class PersonalOAuthScopeMismatchLoggingReceiver:
    """Logs the sanitized scope mismatch fact as a warning for administrators."""

    def __call__(self, event: PersonalOAuthScopeMismatchObserved) -> None:
        logging.getLogger("umbod.personal_oauth").warning(
            "Personal OAuth provider scopes do not match the configured request",
            extra={"structured_attributes": {
                "event.name": "personal_oauth.scope_mismatch",
                "connector.id": event.connector_id,
                "oauth.step": event.step,
                "reason": "scope_mismatch",
                "oauth.scopes.configured": " ".join(event.configured_scopes),
                "oauth.scopes.configured_count": len(event.configured_scopes),
                "oauth.scopes.returned": " ".join(event.returned_scopes),
                "oauth.scopes.returned_count": len(event.returned_scopes),
            }},
        )


def create_personal_oauth_diagnostics_signal() -> Signal[PersonalOAuthScopeMismatchObserved]:
    signal = Signal[PersonalOAuthScopeMismatchObserved](
        PublishingSignalFailureHandler(create_application_failure_signal()),
    )
    signal.connect(SCOPE_MISMATCH_LOGGING_RECEIVER, PersonalOAuthScopeMismatchLoggingReceiver())
    return signal
