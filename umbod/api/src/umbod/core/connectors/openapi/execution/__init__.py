from importlib import import_module
from typing import Any

__all__ = [
    "AggregateOpenApiOperationResolver",
    "ApprovedOpenApiOperation",
    "AsyncStreamingHttpClient",
    "AuthenticatedOutboundRequest",
    "BearerOpenApiRequestAuthenticator",
    "ExactGroupOpenApiCapabilityAuthorizer",
    "ExactHttpsDestinationPolicy",
    "HttpxOutboundOperationAdapter",
    "HttpxSpecificationFetcher",
    "IdentityOpenApiResponseNormalizer",
    "MissingJsonBody",
    "NoTrustedAuthorization",
    "OpenApiCapabilityExecutionResult",
    "OpenApiCapabilityExecutionService",
    "OpenApiCapabilityUnavailable",
    "OpenApiExecutionLimits",
    "OpenApiExecutionResponse",
    "OpenApiOperationArguments",
    "OpenApiOperationInput",
    "OpenApiParameterSerializer",
    "OpenApiRequestAuthenticator",
    "OpenApiRequestCompiler",
    "OpenApiResponseNormalizer",
    "OpenApiValueValidator",
    "OutboundHttpClientFactory",
    "OutboundNetworkError",
    "OutboundOperationTransport",
    "OutboundPolicyError",
    "OutboundRedirectError",
    "OutboundRequest",
    "OutboundTimeoutError",
    "OutboundTlsError",
    "OutboundTransportError",
    "PresentJsonBody",
    "SUPPORTED_PARAMETER_SERIALIZATION",
    "SpecificationFetchRequest",
    "SpecificationFetcher",
    "StrictOpenApiRequestCompiler",
    "TrustedBearerAuthorization",
    "UnauthenticatedOpenApiRequestAuthenticator",
]

_EXPORTS: dict[str, str] = {
    "AggregateOpenApiOperationResolver": ".service",
    "ApprovedOpenApiOperation": ".service",
    "AsyncStreamingHttpClient": ".http_adapters",
    "AuthenticatedOutboundRequest": ".authentication",
    "BearerOpenApiRequestAuthenticator": ".authentication",
    "ExactGroupOpenApiCapabilityAuthorizer": ".service",
    "ExactHttpsDestinationPolicy": ".service",
    "HttpxOutboundOperationAdapter": ".http_adapters",
    "HttpxSpecificationFetcher": ".http_adapters",
    "IdentityOpenApiResponseNormalizer": ".service",
    "MissingJsonBody": ".service",
    "NoTrustedAuthorization": ".authentication",
    "OpenApiCapabilityExecutionResult": ".service",
    "OpenApiCapabilityExecutionService": ".service",
    "OpenApiCapabilityUnavailable": ".service",
    "OpenApiExecutionLimits": ".service",
    "OpenApiExecutionResponse": ".service",
    "OpenApiOperationArguments": ".service",
    "OpenApiOperationInput": ".service",
    "OpenApiParameterSerializer": ".request_values",
    "OpenApiRequestAuthenticator": ".authentication",
    "OpenApiRequestCompiler": ".service",
    "OpenApiResponseNormalizer": ".service",
    "OpenApiValueValidator": ".request_values",
    "OutboundHttpClientFactory": ".http_adapters",
    "OutboundNetworkError": ".http_adapters",
    "OutboundOperationTransport": ".service",
    "OutboundPolicyError": ".http_adapters",
    "OutboundRedirectError": ".http_adapters",
    "OutboundRequest": ".authentication",
    "OutboundTimeoutError": ".http_adapters",
    "OutboundTlsError": ".http_adapters",
    "OutboundTransportError": ".http_adapters",
    "PresentJsonBody": ".service",
    "SUPPORTED_PARAMETER_SERIALIZATION": ".parameter_serialization",
    "SpecificationFetchRequest": ".http_adapters",
    "SpecificationFetcher": ".http_adapters",
    "StrictOpenApiRequestCompiler": ".service",
    "TrustedBearerAuthorization": ".authentication",
    "UnauthenticatedOpenApiRequestAuthenticator": ".authentication",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
