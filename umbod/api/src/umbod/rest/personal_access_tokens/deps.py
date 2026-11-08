from typing import Annotated

from fastapi import Depends

from umbod.config.identity_policy import local_development_identity_enabled
from umbod.core.persistence import Database
from umbod.core.personal_access_tokens.ownership import (
    LocalDevelopmentPersonalAccessTokenOwnerResolver,
    VerifiedPersonalAccessTokenOwnerResolver,
)
from umbod.core.personal_access_tokens.ports import PersonalAccessTokenOwnerResolver
from umbod.core.personal_access_tokens import PersonalAccessTokenService
from umbod.core.personal_access_tokens.factory import (
    create_personal_access_token_service,
)
from umbod.core.personal_access_tokens.access import personal_access_token_policy
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories

from .errors import token_operation


async def get_personal_access_token_database(
    factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> Database:
    async with token_operation():
        await factories.persistence_runtime.readiness.ensure_ready()
    return factories.persistence_runtime.database


def get_personal_access_token_owner_resolver(
    factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> PersonalAccessTokenOwnerResolver:
    if local_development_identity_enabled(factories.settings):
        return LocalDevelopmentPersonalAccessTokenOwnerResolver(
            factories.settings.admin_authentication.simulated_user_id
        )
    return VerifiedPersonalAccessTokenOwnerResolver()


def get_personal_access_token_service(
    database: Annotated[Database, Depends(get_personal_access_token_database)],
    owner_resolver: Annotated[
        PersonalAccessTokenOwnerResolver, Depends(get_personal_access_token_owner_resolver)
    ],
) -> PersonalAccessTokenService:
    return create_personal_access_token_service(
        database, personal_access_token_policy(), owner_resolver=owner_resolver
    )
