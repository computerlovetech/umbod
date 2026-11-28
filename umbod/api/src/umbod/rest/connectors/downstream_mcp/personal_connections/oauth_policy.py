from typing import Annotated

from fastapi import Depends
from pydantic import ConfigDict, StrictBool

from umbod.proxies import Model

from .dependencies import Factories


class PersonalOAuthPolicy(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: StrictBool


def get_personal_oauth_policy(factories: Factories) -> PersonalOAuthPolicy:
    settings = factories.settings.personal_connections
    return PersonalOAuthPolicy(enabled=settings.enabled and settings.oauth_enabled)


OAuthPolicy = Annotated[PersonalOAuthPolicy, Depends(get_personal_oauth_policy)]
