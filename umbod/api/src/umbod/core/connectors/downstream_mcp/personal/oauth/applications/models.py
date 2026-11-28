from typing import Annotated, Literal

from pydantic import AwareDatetime, ConfigDict, Field, SecretStr, field_validator

from umbod.proxies import Model

from ..configuration import OAuthClientId, OAuthIssuer, OAuthScopes
from ..callback import OAuthCallbackURI


class ApplicationModel(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AbsentApplicationReference(ApplicationModel):
    kind: Literal["absent"] = "absent"


class RegisteredApplicationReference(ApplicationModel):
    kind: Literal["registered"] = "registered"
    registration_id: str = Field(min_length=1, max_length=128)


ApplicationReference = Annotated[
    AbsentApplicationReference | RegisteredApplicationReference, Field(discriminator="kind")
]


class OAuthApplicationBinding(ApplicationModel):
    connector_id: str = Field(min_length=1)
    configuration_revision: str = Field(min_length=1, max_length=128)
    issuer: OAuthIssuer
    resource: OAuthIssuer
    redirect_uri: OAuthCallbackURI
    token_endpoint: OAuthIssuer
    requested_scopes: OAuthScopes
    token_endpoint_auth_method: Literal["client_secret_basic", "client_secret_post"]


class NonexpiringApplicationSecret(ApplicationModel):
    kind: Literal["nonexpiring"] = "nonexpiring"


class ExpiringApplicationSecret(ApplicationModel):
    kind: Literal["expiring"] = "expiring"
    expires_at: AwareDatetime


class OAuthApplicationCredentials(ApplicationModel):
    client_id: OAuthClientId
    client_secret: SecretStr = Field(min_length=1, max_length=4096)
    lifetime: Annotated[
        NonexpiringApplicationSecret | ExpiringApplicationSecret, Field(discriminator="kind")
    ]

    @field_validator("client_secret")
    @classmethod
    def validate_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if not secret.strip() or any(ord(character) < 32 or ord(character) == 127 for character in secret):
            raise ValueError("Invalid application secret")
        return value


class ClaimedOAuthApplication(ApplicationModel):
    kind: Literal["claimed"] = "claimed"
    registration_id: str = Field(min_length=1)
    claim_id: str = Field(min_length=1)
    binding: OAuthApplicationBinding


class ReadyOAuthApplication(ApplicationModel):
    kind: Literal["ready"] = "ready"
    registration_id: str = Field(min_length=1)
    binding: OAuthApplicationBinding
    credentials: OAuthApplicationCredentials


class ResolveOAuthApplication(ApplicationModel):
    reference: RegisteredApplicationReference
    binding: OAuthApplicationBinding
    client_id: OAuthClientId


class CompleteOAuthApplication(ApplicationModel):
    claim: ClaimedOAuthApplication
    credentials: OAuthApplicationCredentials


class OAuthApplicationUnavailable(ValueError):
    pass
