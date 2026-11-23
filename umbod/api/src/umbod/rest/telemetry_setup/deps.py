import re
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException

from umbod.core.callers import CallerContext
from umbod.core.personal_access_tokens import UntrustedPersonalAccessTokenCaller
from umbod.core.personal_access_tokens.models import TokenOwner
from umbod.core.personal_access_tokens.ports import PersonalAccessTokenOwnerResolver
from umbod.rest.authentication.deps import get_caller_context
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.personal_access_tokens.deps import get_personal_access_token_owner_resolver

from .models import AvailableTelemetrySetup, TelemetrySetup, UnavailableTelemetrySetup


def get_telemetry_owner(
    caller: Annotated[CallerContext, Depends(get_caller_context)],
    owner_resolver: Annotated[
        PersonalAccessTokenOwnerResolver, Depends(get_personal_access_token_owner_resolver)
    ],
) -> TokenOwner:
    try:
        return owner_resolver.resolve(caller)
    except UntrustedPersonalAccessTokenCaller:
        raise HTTPException(status_code=403, detail="Verified identity required") from None


def get_telemetry_setup_configuration(
    factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> TelemetrySetup:
    settings = factories.settings
    if not settings.otlp_receiver.enabled:
        return UnavailableTelemetrySetup(status="unavailable", reason="disabled")
    base_url = settings.endpoints.collector_base_url
    if not base_url:
        return UnavailableTelemetrySetup(status="unavailable", reason="not_configured")
    endpoint = base_url + "/v1/logs"
    if (
        len(endpoint) > 2048
        or re.fullmatch(r"[A-Za-z0-9:/._~!&'()*+,;=@%\[\]-]+", endpoint) is None
        or re.search(r"%(?:[01][0-9a-f]|7f)|%(?![0-9a-f]{2})", endpoint, re.IGNORECASE)
        or re.fullmatch(r"(?:\[[A-Fa-f0-9:.]+\]|[A-Za-z0-9.-]+)(?::[0-9]+)?", urlsplit(endpoint).netloc) is None
    ):
        return UnavailableTelemetrySetup(status="unavailable", reason="not_configured")
    return AvailableTelemetrySetup(status="available", logs_endpoint=endpoint)


def get_telemetry_setup(
    owner: Annotated[TokenOwner, Depends(get_telemetry_owner)],
    configuration: Annotated[TelemetrySetup, Depends(get_telemetry_setup_configuration)],
) -> TelemetrySetup:
    return configuration
