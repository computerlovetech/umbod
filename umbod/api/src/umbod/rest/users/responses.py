from typing import Optional

from pydantic import Field
from umbod.rest.proxies import Model


class CurrentUserResponse(Model):
    id: str = Field(description="Unique identifier of the authenticated user.")
    email: Optional[str] = Field(description="Email address of the authenticated user.")
    name: str = Field(description="Display name of the authenticated user.")
    picture: Optional[str] = Field(
        description="Profile picture URL of the authenticated user."
    )


class UserCapabilitiesResponse(Model):
    administration: bool


class UserProfileResponse(Model):
    user: CurrentUserResponse
    capabilities: UserCapabilitiesResponse
