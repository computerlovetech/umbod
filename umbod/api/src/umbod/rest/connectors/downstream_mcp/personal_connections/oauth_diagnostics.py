from typing import Annotated

from fastapi import Depends, FastAPI

from umbod.core.connectors.downstream_mcp.personal.oauth.diagnostics import PersonalOAuthFailureObserver
from umbod.core.diagnostics import ApplicationFailure, CorrelatedFailureContext, NoFailureContext
from umbod.core.diagnostics.oauth import PublishingOAuthFailureObserver
from umbod.core.signals import SignalPublisher
from umbod.http_metadata import current_request_id


def get_oauth_application_failures() -> SignalPublisher[ApplicationFailure]:
    raise RuntimeError("OAuth application diagnostics are not composed")


def get_oauth_failure_observer(
    publisher: Annotated[SignalPublisher[ApplicationFailure], Depends(get_oauth_application_failures)],
) -> PersonalOAuthFailureObserver:
    request_id = current_request_id()
    correlation = CorrelatedFailureContext(request_id, None) if request_id is not None else NoFailureContext()
    return PublishingOAuthFailureObserver(publisher, correlation, operation="authorize")


def get_setup_failure_observer(
    publisher: Annotated[SignalPublisher[ApplicationFailure], Depends(get_oauth_application_failures)],
) -> PersonalOAuthFailureObserver:
    request_id = current_request_id()
    correlation = CorrelatedFailureContext(request_id, None) if request_id is not None else NoFailureContext()
    return PublishingOAuthFailureObserver(publisher, correlation, operation="validate_setup")


def install_oauth_diagnostics(app: FastAPI, publisher: SignalPublisher[ApplicationFailure]) -> None:
    def provide_application_failures() -> SignalPublisher[ApplicationFailure]:
        return publisher

    app.dependency_overrides[get_oauth_application_failures] = provide_application_failures
