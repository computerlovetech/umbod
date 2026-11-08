from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from umbod.core.personal_access_tokens.access import (
    PersonalAccessTokenPermission,
    PersonalAccessTokenResource,
)

from umbod.core.personal_access_tokens.models import (
    BoundedText,
    PersonalAccessTokenMetadata,
    UtcDatetime,
)


class CreatePersonalAccessToken(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    name: BoundedText
    expires_at: UtcDatetime
    permissions: Annotated[
        dict[PersonalAccessTokenResource, PersonalAccessTokenPermission],
        Field(min_length=1),
    ]


class CreatedPersonalAccessToken(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    metadata: PersonalAccessTokenMetadata
    token: str = Field(repr=False)
