from typing import Annotated

from pydantic import ConfigDict, Field

from umbod.proxies import Model
from umbod.core.credential_expiry import CredentialExpiry
from umbod.core.personal_access_tokens.access import (
    PersonalAccessTokenPermission,
    PersonalAccessTokenResource,
)

from umbod.core.personal_access_tokens.models import (
    BoundedText,
    PersonalAccessTokenMetadata,
)


class CreatePersonalAccessToken(Model):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    name: BoundedText
    expires_at: CredentialExpiry
    permissions: Annotated[
        dict[PersonalAccessTokenResource, PersonalAccessTokenPermission],
        Field(min_length=1),
    ]


class CreatedPersonalAccessToken(Model):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    metadata: PersonalAccessTokenMetadata
    token: str = Field(repr=False)
