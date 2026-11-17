from typing import Literal

from pydantic import BaseModel, ConfigDict

from umbod.core.invocation.diagnostics import DownstreamResponseEvidence

from umbod.core.connectors.downstream_mcp.personal_oauth_configuration.models import OAuthScopes, PersonalOAuthPolicy


class SetupModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DiscoverPersonalOAuthSetup(SetupModel):
    endpoint_url: str
    redirect_uri: str
    policy: PersonalOAuthPolicy


class ValidatePersonalOAuthSetup(DiscoverPersonalOAuthSetup):
    pass


class PersonalOAuthSetupDiscovery(SetupModel):
    issuer_url: str
    redirect_uri: str
    available_scopes: OAuthScopes
    registration_mode: Literal["dynamic_public", "dynamic_confidential", "preconfigured_public", "preconfigured_confidential"]


class ValidatedPersonalOAuthSetup(SetupModel):
    kind: Literal["validated"] = "validated"
    discovery: PersonalOAuthSetupDiscovery
    returned_scopes: OAuthScopes
    scope_source: Literal["registration", "not_returned", "not_checked"]


class PersonalOAuthSetupScopeMismatch(SetupModel):
    kind: Literal["scope_mismatch"] = "scope_mismatch"
    discovery: PersonalOAuthSetupDiscovery
    returned_scopes: OAuthScopes
    downstream_response: DownstreamResponseEvidence


PersonalOAuthSetupValidation = ValidatedPersonalOAuthSetup | PersonalOAuthSetupScopeMismatch
