from pydantic import Field
from umbod.rest.proxies import Model


class CurrentUserResponse(Model):
    """Authenticated user details returned by the current-user endpoint."""

    id: str = Field(description="Unique identifier of the authenticated user.")
    email: str = Field(description="Email address of the authenticated user.")
    name: str = Field(description="Display name of the authenticated user.")
    picture: str | None = Field(
        default=None, description="Profile picture URL of the authenticated user."
    )
