from typing import Annotated

from fastapi import Depends, HTTPException

from umbod.core.callers import CallerContext
from umbod.core.personal_access_tokens import UntrustedPersonalAccessTokenCaller
from umbod.core.personal_access_tokens.ports import PersonalAccessTokenOwnerResolver
from umbod.rest.authentication.deps import get_caller_context
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.personal_access_tokens.deps import get_personal_access_token_owner_resolver

from .models import AvailableTelemetrySetup, TelemetrySetup, UnavailableTelemetrySetup


def get_telemetry_setup(
    caller: Annotated[CallerContext, Depends(get_caller_context)],
    owner_resolver: Annotated[
        PersonalAccessTokenOwnerResolver, Depends(get_personal_access_token_owner_resolver)
    ],
    factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> TelemetrySetup:
    try:
        owner_resolver.resolve(caller)
    except UntrustedPersonalAccessTokenCaller:
        raise HTTPException(status_code=403, detail="Verified identity required") from None
    settings = factories.settings
    if not settings.otlp_receiver.enabled:
        return UnavailableTelemetrySetup(status="unavailable", reason="disabled")
    if not settings.endpoints.collector_base_url:
        return UnavailableTelemetrySetup(status="unavailable", reason="not_configured")
    return AvailableTelemetrySetup(
        status="available",
        logs_endpoint=settings.endpoints.collector_base_url + "/v1/logs",
    )
