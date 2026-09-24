import ipaddress
import asyncio
import re
from functools import partial
from typing import Literal, Protocol, TypeAlias
from urllib.parse import quote, urlsplit, urlunsplit

from pydantic import ConfigDict, JsonValue, PositiveFloat, PositiveInt

from umbod.proxies import Model
from umbod.core.capabilities import CapabilityIdentity
from umbod.core.invocation.tools.execution import PreparedToolExecution, ToolExecutionPipeline, ToolExecutionRequest, prepare_tool_execution
from umbod.core.connectors.openapi.execution.authentication import (
    AuthenticatedOutboundRequest,
    BearerOpenApiRequestAuthenticator as BearerOpenApiRequestAuthenticator,
    NoTrustedAuthorization as NoTrustedAuthorization,
    OpenApiRequestAuthenticator,
    OutboundRequest,
    TrustedBearerAuthorization as TrustedBearerAuthorization,
    UnauthenticatedOpenApiRequestAuthenticator as UnauthenticatedOpenApiRequestAuthenticator,
)
from umbod.core.connectors.openapi.models import OpenApiEndpointCapability, OpenApiParameter
from umbod.core.connectors.openapi.execution.parameter_serialization import (
    OpenApiParameterSerializationPolicy,
)
from umbod.core.connectors.openapi.execution.request_values import (
    OpenApiParameterSerializer,
    OpenApiValueValidator,
)
from umbod.core.connectors.openapi.stores.catalog_models import (
    OpenApiCatalogHeader,
    PersistedOpenApiOperation,
)
from umbod.core.connectors.openapi.stores import (
    CurrentOpenApiCatalogHeaderReader,
    OpenApiOperationReader,
)


class MissingJsonBody(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: Literal["missing"] = "missing"


class PresentJsonBody(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: Literal["present"] = "present"
    value: JsonValue


RequestBody: TypeAlias = MissingJsonBody | PresentJsonBody


class OpenApiOperationArguments(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: dict[str, JsonValue]
    query: dict[str, JsonValue]
    headers: dict[str, JsonValue]
    body: RequestBody


class ApprovedOpenApiOperation(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    operation_id: str
    endpoint: OpenApiEndpointCapability
    server_url: str
    approved_hosts: tuple[str, ...]


class OpenApiOperationInput(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    operation_id: str
    path: dict[str, JsonValue]
    query: dict[str, JsonValue]
    headers: dict[str, JsonValue]
    body: RequestBody


class OpenApiExecutionLimits(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    timeout_seconds: PositiveFloat
    maximum_response_bytes: PositiveInt


class OpenApiExecutionResponse(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: int
    content_type: str
    headers: dict[str, str]
    body: bytes
    truncated: bool


class ExactOpenApiCapabilityAuthorizer(Protocol):
    async def allows(
        self, groups: tuple[str, ...], connector_id: str, operation_id: str
    ) -> bool: ...


class ActiveOpenApiOperationResolver(Protocol):
    def resolve(
        self,
        connector_id: str,
        operation: PersistedOpenApiOperation,
        header: OpenApiCatalogHeader,
    ) -> ApprovedOpenApiOperation: ...


class OpenApiRequestCompiler(Protocol):
    def compile(
        self,
        operation: ApprovedOpenApiOperation,
        arguments: OpenApiOperationArguments,
        limits: OpenApiExecutionLimits,
    ) -> OutboundRequest: ...


class OutboundOperationTransport(Protocol):
    async def send(self, request: AuthenticatedOutboundRequest) -> OpenApiExecutionResponse: ...


class OpenApiResponseNormalizer(Protocol):
    def normalize(self, response: OpenApiExecutionResponse) -> OpenApiExecutionResponse: ...


class IdentityOpenApiResponseNormalizer:
    def normalize(self, response: OpenApiExecutionResponse) -> OpenApiExecutionResponse:
        return response


class ExactHttpsDestinationPolicy:
    def validate(self, url: str, approved_hosts: tuple[str, ...]) -> str:
        normalized_approved_hosts = frozenset(
            self._normalize_approved_host(host) for host in approved_hosts
        )
        if not normalized_approved_hosts:
            raise ValueError("At least one approved host is required")
        parsed = urlsplit(url)
        try:
            host = parsed.hostname
            port = parsed.port
        except ValueError as error:
            raise ValueError("Destination is malformed") from error
        if parsed.scheme.lower() != "https" or host is None:
            raise ValueError("Destination must use HTTPS")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("Destination userinfo is forbidden")
        if parsed.fragment:
            raise ValueError("Destination fragment is forbidden")
        if port not in (None, 443):
            raise ValueError("Destination must use the default HTTPS port")
        if host.endswith("."):
            raise ValueError("Destination trailing dot is forbidden")
        normalized_host = self._canonical_host(host)
        if normalized_host not in normalized_approved_hosts:
            raise ValueError("Destination host is not approved")
        netloc = normalized_host if port is None else f"{normalized_host}:443"
        return urlunsplit(("https", netloc, parsed.path, parsed.query, ""))

    def _normalize_approved_host(self, host: str) -> str:
        try:
            return self._canonical_host(host)
        except ValueError as error:
            raise ValueError("Approved host is malformed") from error

    def _canonical_host(self, host: str) -> str:
        if (
            not host.isascii()
            or host != host.strip()
            or host.endswith(".")
            or "*" in host
            or len(host) > 253
        ):
            raise ValueError("Host is malformed")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError("IP literal is forbidden")
        labels = host.split(".")
        if len(labels) < 2 or any(
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or not label.replace("-", "").isalnum()
            for label in labels
        ):
            raise ValueError("Host is malformed")
        return host.lower()


class ExactGroupOpenApiCapabilityAuthorizer:
    def __init__(self, permission_reader: object) -> None:
        self._permission_reader = permission_reader

    async def allows(self, groups: tuple[str, ...], connector_id: str, operation_id: str) -> bool:
        from umbod.core.permissions.domain import ConnectorToolRef

        tool = ConnectorToolRef(connector_id, operation_id)
        for group in dict.fromkeys(groups):
            permissions = await self._permission_reader.list_group_permissions(group)
            if connector_id in permissions.connector_ids or tool in permissions.tools:
                return True
        return False


class AggregateOpenApiOperationResolver:
    def resolve(
        self,
        connector_id: str,
        operation: PersistedOpenApiOperation,
        header: OpenApiCatalogHeader,
    ) -> ApprovedOpenApiOperation:
        server = header.selected_server_url
        if server not in header.server_candidates:
            raise ValueError("Capability unavailable")
        return ApprovedOpenApiOperation(
            connector_id=connector_id,
            operation_id=operation.summary.operation_id,
            endpoint=operation.capability,
            server_url=server,
            approved_hosts=header.approved_hosts,
        )


class StrictOpenApiRequestCompiler:
    _templates = re.compile(r"\{([^{}]+)\}")
    _forbidden_headers = frozenset(
        {
            "authorization",
            "proxy-authorization",
            "host",
            "cookie",
            "forwarded",
            "x-forwarded-for",
            "x-forwarded-host",
            "x-forwarded-proto",
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "te",
            "trailer",
            "transfer-encoding",
            "upgrade",
        }
    )

    def __init__(self, policy: ExactHttpsDestinationPolicy) -> None:
        self._policy = policy
        self._serialization_policy = OpenApiParameterSerializationPolicy()
        self._serializer = OpenApiParameterSerializer()
        self._value_validator = OpenApiValueValidator()

    def compile(
        self,
        operation: ApprovedOpenApiOperation,
        arguments: OpenApiOperationArguments,
        limits: OpenApiExecutionLimits,
    ) -> OutboundRequest:
        endpoint = operation.endpoint
        self._validate_contract(endpoint)
        path = self._compile_path(endpoint, arguments.path)
        query = self._compile_query(endpoint, arguments.query)
        headers = self._compile_headers(endpoint, arguments.headers)
        body, has_body = self._compile_body(endpoint, arguments.body)
        base = self._policy.validate(operation.server_url, operation.approved_hosts)
        url = f"{base.rstrip('/')}/{path.lstrip('/')}"
        if query:
            url = f"{url}?{query}"
        return OutboundRequest(
            method=endpoint.method.upper(),
            url=self._policy.validate(url, operation.approved_hosts),
            headers=headers,
            json_body=body,
            has_json_body=has_body,
            timeout_seconds=limits.timeout_seconds,
            maximum_response_bytes=limits.maximum_response_bytes,
            approved_hosts=operation.approved_hosts,
        )

    def _validate_contract(self, endpoint: OpenApiEndpointCapability) -> None:
        keys = [
            (
                parameter.location,
                parameter.name.lower() if parameter.location == "header" else parameter.name,
            )
            for parameter in endpoint.parameters
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("Malformed operation contract: duplicate parameter")
        declared_paths = {
            parameter.name for parameter in endpoint.parameters if parameter.location == "path"
        }
        templates = self._templates.findall(endpoint.path)
        if len(templates) != len(set(templates)) or set(templates) != declared_paths:
            raise ValueError("Malformed operation contract: path templates do not match parameters")
        if len(endpoint.request_bodies) > 1:
            raise ValueError("Malformed operation contract: multiple request bodies")
        if any(
            not self._serialization_policy.supports(parameter) for parameter in endpoint.parameters
        ):
            raise ValueError("Malformed operation contract: unsupported parameter serialization")

    def _parameters(
        self, endpoint: OpenApiEndpointCapability, location: str
    ) -> dict[str, OpenApiParameter]:
        return {
            parameter.name: parameter
            for parameter in endpoint.parameters
            if parameter.location == location
        }

    def _validate_arguments(
        self, declared: dict[str, OpenApiParameter], supplied: dict[str, JsonValue], location: str
    ) -> None:
        unknown = set(supplied) - set(declared)
        missing = {name for name, parameter in declared.items() if parameter.required} - set(
            supplied
        )
        if unknown:
            raise ValueError(f"Undeclared {location} parameter")
        if missing:
            raise ValueError(f"Missing required {location} parameter")
        for name, value in supplied.items():
            self._value_validator.validate(
                value, declared[name].capability_schema, f"{location}.{name}"
            )

    def _compile_path(
        self, endpoint: OpenApiEndpointCapability, supplied: dict[str, JsonValue]
    ) -> str:
        declared = self._parameters(endpoint, "path")
        self._validate_arguments(declared, supplied, "path")
        result = endpoint.path
        for name in sorted(supplied):
            serialized = self._serializer.simple(declared[name], supplied[name])
            result = result.replace("{" + name + "}", quote(serialized, safe=""))
        if self._templates.search(result):
            raise ValueError("Unresolved path template")
        return result

    def _compile_query(
        self, endpoint: OpenApiEndpointCapability, supplied: dict[str, JsonValue]
    ) -> str:
        declared = self._parameters(endpoint, "query")
        self._validate_arguments(declared, supplied, "query")
        pairs: list[tuple[str, str]] = []
        for name in sorted(supplied):
            pairs.extend(self._serializer.query(declared[name], supplied[name]))
        return self._serializer.encode_query(pairs)

    def _compile_headers(
        self, endpoint: OpenApiEndpointCapability, supplied: dict[str, JsonValue]
    ) -> dict[str, str]:
        lowered: dict[str, JsonValue] = {}
        originals: dict[str, str] = {}
        for name, value in supplied.items():
            normalized = name.lower()
            if normalized in lowered:
                raise ValueError("Duplicate header parameter")
            lowered[normalized] = value
            originals[normalized] = name
        declared_parameters = [item for item in endpoint.parameters if item.location == "header"]
        declared = {item.name.lower(): item for item in declared_parameters}
        if set(declared) & self._forbidden_headers or set(lowered) & self._forbidden_headers:
            raise ValueError("Security-sensitive header is forbidden")
        unknown = set(lowered) - set(declared)
        missing = {name for name, parameter in declared.items() if parameter.required} - set(
            lowered
        )
        if unknown:
            raise ValueError("Undeclared header parameter")
        if missing:
            raise ValueError("Missing required header parameter")
        result: dict[str, str] = {}
        for name in sorted(lowered):
            self._value_validator.validate(
                lowered[name], declared[name].capability_schema, f"header.{name}"
            )
            result[name] = self._serializer.simple(declared[name], lowered[name])
        return result

    def _compile_body(
        self, endpoint: OpenApiEndpointCapability, body: RequestBody
    ) -> tuple[JsonValue, bool]:
        if not endpoint.request_bodies:
            if isinstance(body, PresentJsonBody):
                raise ValueError("Operation does not declare a JSON request body")
            return {}, False
        contract = endpoint.request_bodies[0]
        if contract.media_type != "application/json":
            raise ValueError("Unsupported request body media type")
        if isinstance(body, MissingJsonBody):
            if contract.required:
                raise ValueError("Missing required JSON request body")
            return {}, False
        self._value_validator.validate(body.value, contract.capability_schema, "body")
        return body.value, True


OpenApiExecutionErrorCode = Literal[
    "capability_unavailable",
    "invalid_arguments",
    "outbound_failed",
    "outbound_timeout",
    "outbound_unavailable",
    "outbound_tls_failed",
    "destination_denied",
    "redirect_denied",
]


class OpenApiCapabilityExecutionResult(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["success", "error"]
    code: OpenApiExecutionErrorCode | None = None
    message: str
    http_status: int | None = None
    content_type: str | None = None
    response_size_bytes: int = 0
    truncated: bool = False


class OpenApiCapabilityUnavailable(Exception):
    pass


class OpenApiCapabilityExecutionService:
    def __init__(
        self,
        active_catalog_reader: CurrentOpenApiCatalogHeaderReader | OpenApiOperationReader,
        authorizer: ExactOpenApiCapabilityAuthorizer,
        resolver: ActiveOpenApiOperationResolver,
        compiler: OpenApiRequestCompiler,
        transport: OutboundOperationTransport,
        normalizer: OpenApiResponseNormalizer,
        limits: OpenApiExecutionLimits,
        authenticator: OpenApiRequestAuthenticator,
        execution_pipeline: ToolExecutionPipeline[OpenApiExecutionResponse],
    ) -> None:
        self._active_catalog_reader = active_catalog_reader
        self._authorizer = authorizer
        self._resolver = resolver
        self._compiler = compiler
        self._transport = transport
        self._normalizer = normalizer
        self._limits = limits
        self._authenticator = authenticator
        self._execution_pipeline = execution_pipeline

    async def execute(
        self, operation_input: OpenApiOperationInput, groups: tuple[str, ...]
    ) -> OpenApiCapabilityExecutionResult:
        request = self._execution_request(operation_input)
        try:
            response = await self._execution_pipeline.execute(
                request,
                partial(self._prepare_execution, operation_input, groups),
            )
            return self._success_result(response)
        except asyncio.CancelledError:
            raise
        except OpenApiCapabilityUnavailable:
            return self._error("capability_unavailable")
        except ValueError:
            return self._error("invalid_arguments")
        except Exception as error:
            return self._error(self._safe_error_code(error))

    @staticmethod
    def _execution_request(operation_input: OpenApiOperationInput) -> ToolExecutionRequest:
        return ToolExecutionRequest(
            identity=CapabilityIdentity(
                connector_kind="openapi",
                connector_id=operation_input.connector_id,
                capability_kind="tool",
            capability_key=operation_input.operation_id,
            ),
            public_tool_name="execute_openapi",
            arguments=operation_input.model_dump(mode="python"),
        )

    @staticmethod
    def _success_result(response: OpenApiExecutionResponse) -> OpenApiCapabilityExecutionResult:
        return OpenApiCapabilityExecutionResult(
            status="success",
            message="OpenAPI capability executed.",
            http_status=response.status,
            content_type=response.content_type,
            response_size_bytes=len(response.body),
            truncated=response.truncated,
        )

    async def _prepare_execution(
        self,
        operation_input: OpenApiOperationInput,
        groups: tuple[str, ...],
    ) -> PreparedToolExecution[OpenApiExecutionResponse]:
        if not await self._authorizer.allows(
            groups, operation_input.connector_id, operation_input.operation_id
        ):
            raise OpenApiCapabilityUnavailable
        operation = await self._resolve_operation(operation_input)
        outbound_request = self._compiler.compile(
            operation,
            OpenApiOperationArguments(
                path=operation_input.path,
                query=operation_input.query,
                headers=operation_input.headers,
                body=operation_input.body,
            ),
            self._limits,
        )
        return prepare_tool_execution(
            operation_input.model_dump(mode="python"),
            partial(
                self._invoke_transport,
                operation_input.connector_id,
                outbound_request,
            ),
            operation_input.model_dump(mode="python"),
        )

    async def _resolve_operation(
        self, operation_input: OpenApiOperationInput
    ) -> ApprovedOpenApiOperation:
        persisted = await self._active_catalog_reader.read_operation(
            operation_input.connector_id, operation_input.operation_id
        )
        header = await self._active_catalog_reader.read_current_catalog_header(
            operation_input.connector_id
        )
        if persisted is None or header is None:
            raise OpenApiCapabilityUnavailable
        try:
            return self._resolver.resolve(operation_input.connector_id, persisted, header)
        except ValueError as error:
            raise OpenApiCapabilityUnavailable from error

    async def _invoke_transport(
        self,
        connector_id: str,
        outbound_request: OutboundRequest,
    ) -> OpenApiExecutionResponse:
        authenticated_request = await self._authenticator.authenticate(
            connector_id, outbound_request
        )
        return self._normalizer.normalize(await self._transport.send(authenticated_request))

    def _safe_error_code(self, error: Exception) -> OpenApiExecutionErrorCode:
        safe_codes: set[OpenApiExecutionErrorCode] = {
            "outbound_failed",
            "outbound_timeout",
            "outbound_unavailable",
            "outbound_tls_failed",
            "destination_denied",
            "redirect_denied",
        }
        candidate = getattr(error, "code", "outbound_failed")
        return candidate if candidate in safe_codes else "outbound_failed"

    def _error(self, code: OpenApiExecutionErrorCode) -> OpenApiCapabilityExecutionResult:
        return OpenApiCapabilityExecutionResult(
            status="error", code=code, message="OpenAPI capability execution failed."
        )
