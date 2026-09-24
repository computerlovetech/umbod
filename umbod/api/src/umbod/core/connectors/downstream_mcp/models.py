import hashlib
import json
import re
from datetime import datetime
from ipaddress import ip_address
from typing import Annotated, Literal, TypeAlias, Union
from urllib.parse import SplitResult, unquote, urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic.types import JsonValue

from umbod.core.capabilities.descriptions.domain import CapabilityDescription
from umbod.core.capabilities.tools.names import ToolNamePrefix, normalize_tool_name_prefix


NonEmptyString = Annotated[str, Field(min_length=1)]
JsonObject: TypeAlias = dict[str, JsonValue]
StaticTokenHeaderType = Literal["bearer", "basic", "custom"]
_HTTP_FIELD_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


def validate_custom_header_name(value: str) -> str:
    if not _HTTP_FIELD_NAME.fullmatch(value):
        raise ValueError("custom header name must be a valid HTTP field name")
    if value.lower() == "authorization":
        raise ValueError("custom header name must not be Authorization")
    return value


def _validate_json_object(value: JsonObject) -> JsonObject:
    json.dumps(value, allow_nan=False)
    return value


def _validate_https_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https":
        raise ValueError("endpoint URL must use HTTPS")
    _validate_endpoint_parts(parsed)
    return value


def _validate_loopback_http_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "http":
        raise ValueError("development endpoint URL must use HTTP")
    hostname = _validate_endpoint_parts(parsed)
    if hostname != "localhost":
        try:
            if not ip_address(hostname).is_loopback:
                raise ValueError("development HTTP endpoint must be loopback")
        except ValueError as error:
            raise ValueError("development HTTP endpoint must be loopback") from error
    return value


def _validate_endpoint_parts(parsed: SplitResult) -> str:
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("endpoint URL must not contain user-info")
    hostname = parsed.hostname
    if hostname is None or not hostname or any(character.isspace() for character in hostname):
        raise ValueError("endpoint URL must contain a valid host")
    port = parsed.port
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("endpoint URL must contain a valid port")
    if parsed.fragment:
        raise ValueError("endpoint URL must not contain a fragment")
    return hostname


HttpsEndpointUrl = Annotated[NonEmptyString, AfterValidator(_validate_https_endpoint)]
LoopbackDevelopmentHttpEndpointUrl = Annotated[
    NonEmptyString, AfterValidator(_validate_loopback_http_endpoint)
]
EndpointUrl = HttpsEndpointUrl | LoopbackDevelopmentHttpEndpointUrl
ValidatedJsonObject = Annotated[JsonObject, AfterValidator(_validate_json_object)]
PUBLIC_PROXY_PREFIX = "/mcp/proxies/"
_RESERVED_PROXY_SLUGS = frozenset({"mcp", "proxies", "oauth", "health", "assets", ".well-known"})


def _validate_public_path(value: str) -> str:
    if not value.startswith(PUBLIC_PROXY_PREFIX):
        raise ValueError(f"public path must start with {PUBLIC_PROXY_PREFIX}")
    slug = value.removeprefix(PUBLIC_PROXY_PREFIX)
    if unquote(value) != value or "%" in value:
        raise ValueError("public path must not contain percent encoding")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", slug):
        raise ValueError("public path slug must contain lowercase ASCII letters, digits, or hyphens")
    if slug in _RESERVED_PROXY_SLUGS:
        raise ValueError("public path is reserved")
    return value


def default_public_path(connector_id: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", connector_id.lower()).strip("-")[:63]
    if not slug or slug in _RESERVED_PROXY_SLUGS:
        slug = f"connector-{hashlib.sha256(connector_id.encode()).hexdigest()[:12]}"
    return f"{PUBLIC_PROXY_PREFIX}{slug}"


def default_tool_name_prefix(display_name: str) -> str:
    return normalize_tool_name_prefix(display_name)


PublicPath = Annotated[NonEmptyString, AfterValidator(_validate_public_path)]


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ConnectorDefinitionModel(DomainModel):
    connector_id: NonEmptyString
    display_name: NonEmptyString
    tool_name_prefix: ToolNamePrefix
    capability_description: CapabilityDescription
    endpoint_url: EndpointUrl
    public_path: PublicPath

    @model_validator(mode="before")
    @classmethod
    def migrate_public_path(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        migrated = dict(value)
        if "tool_name_prefix" not in migrated:
            migrated["tool_name_prefix"] = default_tool_name_prefix(
                str(migrated.get("display_name", ""))
            )
        if "public_path" not in migrated and "connector_id" in migrated:
            migrated["public_path"] = default_public_path(str(migrated["connector_id"]))
        if "capability_description" not in migrated:
            display_name = str(migrated.get("display_name", "")).strip() or "Downstream MCP"
            migrated["capability_description"] = f"{display_name[:277]} connector capabilities"
        return migrated


class CreateConnectorDefinitionModel(DomainModel):
    display_name: NonEmptyString
    tool_name_prefix: ToolNamePrefix
    capability_description: CapabilityDescription

    @model_validator(mode="before")
    @classmethod
    def default_missing_tool_name_prefix(cls, value: object) -> object:
        if not isinstance(value, dict) or "tool_name_prefix" in value:
            return value
        return {
            **value,
            "tool_name_prefix": default_tool_name_prefix(str(value.get("display_name", ""))),
        }
    endpoint_url: EndpointUrl
    public_path: PublicPath


class NoAuthCreateConnectorDefinition(CreateConnectorDefinitionModel):
    auth_type: Literal["none"] = "none"


class StaticBearerCreateConnectorDefinition(CreateConnectorDefinitionModel):
    auth_type: Literal["static_bearer"] = "static_bearer"
    header_type: StaticTokenHeaderType = "bearer"
    custom_header_name: str | None = None
    bearer_token: SecretStr

    @model_validator(mode="after")
    def validate_header_configuration(self) -> "StaticBearerCreateConnectorDefinition":
        if self.header_type == "custom":
            if self.custom_header_name is None:
                raise ValueError("custom header name is required")
            validate_custom_header_name(self.custom_header_name)
        elif self.custom_header_name is not None:
            raise ValueError("custom header name is forbidden")
        return self


class OAuthCreateConnectorDefinition(CreateConnectorDefinitionModel):
    """An already authorized connection; browser interaction precedes creation."""

    auth_type: Literal["oauth"] = "oauth"
    authorization: SecretStr


CreateConnectorDefinition = Annotated[
    Union[NoAuthCreateConnectorDefinition, StaticBearerCreateConnectorDefinition, OAuthCreateConnectorDefinition],
    Field(discriminator="auth_type"),
]


class NoAuthConnectorDefinition(ConnectorDefinitionModel):
    auth_type: Literal["none"] = "none"


class StaticBearerConnectorDefinition(ConnectorDefinitionModel):
    auth_type: Literal["static_bearer"] = "static_bearer"
    header_type: StaticTokenHeaderType = "bearer"
    custom_header_name: str | None = None

    @model_validator(mode="after")
    def validate_header_configuration(self) -> "StaticBearerConnectorDefinition":
        if self.header_type == "custom":
            if self.custom_header_name is None:
                raise ValueError("custom header name is required")
            validate_custom_header_name(self.custom_header_name)
        elif self.custom_header_name is not None:
            raise ValueError("custom header name is forbidden")
        return self


class OAuthConnectorDefinition(ConnectorDefinitionModel):
    auth_type: Literal["oauth"] = "oauth"


ConnectorDefinition = Annotated[
    Union[NoAuthConnectorDefinition, StaticBearerConnectorDefinition, OAuthConnectorDefinition],
    Field(discriminator="auth_type"),
]


class NoAuthCredentialState(DomainModel):
    auth_type: Literal["none"] = "none"
    connector_id: NonEmptyString


class StaticBearerCredentialState(DomainModel):
    auth_type: Literal["static_bearer"] = "static_bearer"
    connector_id: NonEmptyString
    bearer_token: SecretStr

    @field_validator("bearer_token")
    @classmethod
    def validate_bearer_token(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("bearer token must not be empty")
        return value


class OAuthCredentialState(DomainModel):
    auth_type: Literal["oauth"] = "oauth"
    connector_id: NonEmptyString
    # Adapter-owned authorization document, encrypted by the credential store.
    authorization: SecretStr


CredentialState = Annotated[
    Union[NoAuthCredentialState, StaticBearerCredentialState, OAuthCredentialState],
    Field(discriminator="auth_type"),
]


class ToolIdentity(DomainModel):
    connector_id: NonEmptyString
    downstream_name: NonEmptyString


class DiscoveredToolMetadata(DomainModel):
    identity: ToolIdentity
    title: NonEmptyString
    description: str
    input_schema: ValidatedJsonObject
    annotations: ValidatedJsonObject = Field(default_factory=dict)
    icons: tuple[ValidatedJsonObject, ...] = ()
    meta: ValidatedJsonObject = Field(default_factory=dict)
    execution: ValidatedJsonObject = Field(default_factory=dict)


class DiscoveredToolWithoutOutputSchema(DiscoveredToolMetadata):
    output_schema_status: Literal["absent"] = "absent"


class DiscoveredToolWithOutputSchema(DiscoveredToolMetadata):
    output_schema_status: Literal["present"] = "present"
    output_schema: ValidatedJsonObject


DiscoveredTool = Annotated[
    Union[DiscoveredToolWithoutOutputSchema, DiscoveredToolWithOutputSchema],
    Field(discriminator="output_schema_status"),
]


class PromptArgument(DomainModel):
    name: NonEmptyString
    title: str = ""
    description: str = ""
    required: bool = False


class DiscoveredPrompt(DomainModel):
    name: NonEmptyString
    title: NonEmptyString
    description: str
    arguments: tuple[PromptArgument, ...] = ()
    icons: tuple[ValidatedJsonObject, ...] = ()
    meta: ValidatedJsonObject = Field(default_factory=dict)


class DiscoveredResource(DomainModel):
    name: NonEmptyString
    title: NonEmptyString
    uri: NonEmptyString
    description: str
    mime_type: str = ""
    size: int = Field(default=0, ge=0)
    icons: tuple[ValidatedJsonObject, ...] = ()
    annotations: ValidatedJsonObject = Field(default_factory=dict)
    meta: ValidatedJsonObject = Field(default_factory=dict)


class DiscoveredResourceTemplate(DomainModel):
    name: NonEmptyString
    title: NonEmptyString
    uri_template: NonEmptyString
    description: str
    mime_type: str = ""
    icons: tuple[ValidatedJsonObject, ...] = ()
    annotations: ValidatedJsonObject = Field(default_factory=dict)
    meta: ValidatedJsonObject = Field(default_factory=dict)


class DiscoveredServerIcon(DomainModel):
    src: NonEmptyString
    mime_type: str = ""
    sizes: tuple[NonEmptyString, ...] = ()
    theme: str = ""


class ToolCatalogSnapshot(DomainModel):
    connector_id: NonEmptyString
    discovered_at: datetime
    tools: tuple[DiscoveredTool, ...]
    server_icons: tuple[DiscoveredServerIcon, ...] = ()
    prompts: tuple[DiscoveredPrompt, ...] = ()
    resources: tuple[DiscoveredResource, ...] = ()
    resource_templates: tuple[DiscoveredResourceTemplate, ...] = ()

    @model_validator(mode="after")
    def validate_capability_identities(self) -> "ToolCatalogSnapshot":
        identities = tuple(tool.identity for tool in self.tools)
        if len(set((item.connector_id, item.downstream_name) for item in identities)) != len(
            identities
        ):
            raise ValueError("duplicate tool identity")
        if any(identity.connector_id != self.connector_id for identity in identities):
            raise ValueError("tool identity connector does not match catalog connector")
        if len({prompt.name for prompt in self.prompts}) != len(self.prompts):
            raise ValueError("duplicate prompt name")
        if len({resource.uri for resource in self.resources}) != len(self.resources):
            raise ValueError("duplicate resource URI")
        if len({template.uri_template for template in self.resource_templates}) != len(
            self.resource_templates
        ):
            raise ValueError("duplicate resource template URI")
        return self


class CatalogReconciliation(DomainModel):
    connector_id: NonEmptyString
    added: tuple[ToolIdentity, ...]
    changed: tuple[ToolIdentity, ...]
    removed: tuple[ToolIdentity, ...]
    unchanged: tuple[ToolIdentity, ...]


class DiscoverySucceeded(DomainModel):
    status: Literal["succeeded"] = "succeeded"
    snapshot: ToolCatalogSnapshot


class DiscoveryFailed(DomainModel):
    status: Literal["failed"] = "failed"
    connector_id: NonEmptyString
    attempted_at: datetime
    reason: NonEmptyString


DiscoveryResult = Annotated[
    Union[DiscoverySucceeded, DiscoveryFailed], Field(discriminator="status")
]


class ConnectorHealthy(DomainModel):
    status: Literal["healthy"] = "healthy"
    connector_id: NonEmptyString
    checked_at: datetime


class ConnectorUnhealthy(DomainModel):
    status: Literal["unhealthy"] = "unhealthy"
    connector_id: NonEmptyString
    checked_at: datetime
    reason: NonEmptyString


ConnectorHealth = Annotated[
    Union[ConnectorHealthy, ConnectorUnhealthy], Field(discriminator="status")
]


class PreparedCatalogConnector(DomainModel):
    result_type: Literal["catalog"] = "catalog"
    definition: ConnectorDefinition
    credential: CredentialState
    snapshot: ToolCatalogSnapshot
    health: ConnectorHealthy


PreparedConnector = PreparedCatalogConnector
