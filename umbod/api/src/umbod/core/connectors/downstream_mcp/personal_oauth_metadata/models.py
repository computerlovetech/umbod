from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..personal_oauth_configuration.models import OAuthIssuer, OAuthScopes


class MetadataModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


MetadataEndpoint = OAuthIssuer
AuthenticationMethod = Annotated[str, Field(min_length=1, max_length=128)]


class AutomaticIssuerSelection(MetadataModel):
    kind: Literal["automatic"]


class SelectedIssuer(MetadataModel):
    kind: Literal["selected"]
    issuer_url: OAuthIssuer


class DiscoverPersonalOAuthMetadata(MetadataModel):
    endpoint_url: MetadataEndpoint
    issuer_selection: Annotated[AutomaticIssuerSelection | SelectedIssuer, Field(discriminator="kind")]


class PersonalOAuthIssuerSelectionRequired(MetadataModel):
    kind: Literal["issuer_selection_required"] = "issuer_selection_required"
    endpoint_url: MetadataEndpoint
    issuer_urls: tuple[OAuthIssuer, ...] = Field(min_length=2, max_length=16)


class DiscoveredPersonalOAuthMetadata(MetadataModel):
    kind: Literal["discovered"] = "discovered"
    endpoint_url: MetadataEndpoint
    issuer_url: OAuthIssuer
    available_scopes: OAuthScopes
    scope_source: Literal["resource", "authorization_server", "unavailable"]
    automatic_registration: Literal["available", "unavailable"]
    token_endpoint_auth_methods: tuple[AuthenticationMethod, ...] = Field(max_length=16)


PersonalOAuthMetadataResult = Annotated[
    PersonalOAuthIssuerSelectionRequired | DiscoveredPersonalOAuthMetadata,
    Field(discriminator="kind"),
]
