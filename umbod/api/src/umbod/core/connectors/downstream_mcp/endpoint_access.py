from typing import Annotated, Literal, Protocol

from pydantic import Field

from .models import DomainModel
from .personal_connections.oauth_models import (
    PersonalOAuthProviderFailure,
    PersonalOAuthProviderUnsupported,
)
from .personal_oauth_metadata import (
    DiscoverPersonalOAuthMetadata,
    PersonalOAuthMetadataProvider,
    PersonalOAuthMetadataResult,
)
from .personal_oauth_metadata.models import AutomaticIssuerSelection, MetadataEndpoint


class CheckMcpEndpointAccess(DomainModel):
    endpoint_url: MetadataEndpoint


class AnonymousInitializationSucceeded(DomainModel):
    kind: Literal["anonymous_initialization_succeeded"] = (
        "anonymous_initialization_succeeded"
    )


class AnonymousAccessRejected(DomainModel):
    kind: Literal["anonymous_access_rejected"] = "anonymous_access_rejected"
    status_code: Literal[401, 403]


class EndpointAccessInconclusive(DomainModel):
    kind: Literal["inconclusive"] = "inconclusive"
    reason: Literal[
        "endpoint_not_found",
        "unreachable",
        "timeout",
        "invalid_mcp_protocol",
        "unsafe_destination",
        "redirected",
        "response_too_large",
    ]


AnonymousInitializationResult = Annotated[
    AnonymousInitializationSucceeded
    | AnonymousAccessRejected
    | EndpointAccessInconclusive,
    Field(discriminator="kind"),
]


class AnonymousMcpInitialization(Protocol):
    async def initialize(
        self, command: CheckMcpEndpointAccess
    ) -> AnonymousInitializationResult: ...


class OAuthDiscovered(DomainModel):
    kind: Literal["oauth_discovered"] = "oauth_discovered"
    metadata: PersonalOAuthMetadataResult


class OAuthNotConfirmed(DomainModel):
    kind: Literal["oauth_not_confirmed"] = "oauth_not_confirmed"


class OAuthNotChecked(DomainModel):
    kind: Literal["oauth_not_checked"] = "oauth_not_checked"


class McpEndpointAccessResult(DomainModel):
    anonymous_initialization: AnonymousInitializationResult
    oauth: Annotated[
        OAuthDiscovered | OAuthNotConfirmed | OAuthNotChecked,
        Field(discriminator="kind"),
    ]


class McpEndpointAccessCheck:
    def __init__(
        self,
        initialization: AnonymousMcpInitialization,
        oauth_metadata: PersonalOAuthMetadataProvider,
    ) -> None:
        self._initialization = initialization
        self._oauth_metadata = oauth_metadata

    async def check(self, command: CheckMcpEndpointAccess) -> McpEndpointAccessResult:
        initialization = await self._initialization.initialize(command)
        if isinstance(initialization, EndpointAccessInconclusive):
            return McpEndpointAccessResult(
                anonymous_initialization=initialization, oauth=OAuthNotChecked()
            )
        oauth = await self._discover_oauth(command)
        return McpEndpointAccessResult(
            anonymous_initialization=initialization, oauth=oauth
        )

    async def _discover_oauth(
        self, command: CheckMcpEndpointAccess
    ) -> OAuthDiscovered | OAuthNotConfirmed:
        try:
            metadata = await self._oauth_metadata.discover(
                DiscoverPersonalOAuthMetadata(
                    endpoint_url=command.endpoint_url,
                    issuer_selection=AutomaticIssuerSelection(kind="automatic"),
                )
            )
        except PersonalOAuthProviderUnsupported, PersonalOAuthProviderFailure:
            return OAuthNotConfirmed()
        return OAuthDiscovered(metadata=metadata)
