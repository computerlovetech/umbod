from typing import Literal, Protocol, TypeAlias

from pydantic import ConfigDict, JsonValue, PositiveFloat, PositiveInt, SecretStr

from umbod.proxies import Model


class OutboundRequest(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    method: str
    url: str
    headers: dict[str, str]
    json_body: JsonValue
    has_json_body: bool
    timeout_seconds: PositiveFloat
    maximum_response_bytes: PositiveInt
    approved_hosts: tuple[str, ...]


class NoTrustedAuthorization(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["none"] = "none"


class TrustedBearerAuthorization(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["bearer"] = "bearer"
    token: SecretStr


TrustedAuthorization: TypeAlias = NoTrustedAuthorization | TrustedBearerAuthorization


class AuthenticatedOutboundRequest(OutboundRequest):
    authorization: TrustedAuthorization


class OpenApiRequestAuthenticator(Protocol):
    async def authenticate(
        self, connector_id: str, request: OutboundRequest
    ) -> AuthenticatedOutboundRequest: ...


class UnauthenticatedOpenApiRequestAuthenticator:
    async def authenticate(
        self, connector_id: str, request: OutboundRequest
    ) -> AuthenticatedOutboundRequest:
        return AuthenticatedOutboundRequest(
            **request.model_dump(), authorization=NoTrustedAuthorization()
        )


class ResolvedBearerConfiguration(Protocol):
    @property
    def bearer_token(self) -> SecretStr: ...


class OpenApiBearerConfigurationResolver(Protocol):
    async def resolve(self, connector_id: str) -> ResolvedBearerConfiguration | None: ...


class BearerOpenApiRequestAuthenticator:
    def __init__(self, configurations: OpenApiBearerConfigurationResolver) -> None:
        self._configurations = configurations

    async def authenticate(
        self, connector_id: str, request: OutboundRequest
    ) -> AuthenticatedOutboundRequest:
        configuration = await self._configurations.resolve(connector_id)
        if configuration is None:
            return await UnauthenticatedOpenApiRequestAuthenticator().authenticate(
                connector_id, request
            )
        return AuthenticatedOutboundRequest(
            **request.model_dump(),
            authorization=TrustedBearerAuthorization(token=configuration.bearer_token),
        )
