from typing import Protocol

from pydantic import BaseModel, ConfigDict

from umbod.rest.authentication.authorization import JwtClaims


class UserProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    email: str
    picture: str


class UserProfileInput(BaseModel):
    access_claims: JwtClaims
    token: str
    header_present: bool


class UserProfileProvider(Protocol):
    def get_profile(self, profile_input: UserProfileInput) -> UserProfile: ...
