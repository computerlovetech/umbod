from typing import Annotated

from fastapi import Depends

from umbod.config.identity_policy import filesystem_managed_issuer
from umbod.core.callers import CallerContext, CallerSnapshot, group_membership_from_values
from umbod.core.filesystem import ContentDriver, FilesystemCreation, Principal, PrincipalType
from umbod.core.filesystem.content import ContentService, FilesystemContent
from umbod.core.filesystem.deletion import DeletionService, FilesystemDeletion
from umbod.core.filesystem.authorization import (
    FilesystemIdentityResolver, LocalDevelopmentIdentityResolver, VerifiedIdentityResolver,
    PermissionDenied, UnresolvedIdentity,
)
from umbod.core.filesystem.browsing import FilesystemBrowsing
from umbod.core.filesystem.sharing import FilesystemSharing
from umbod.core.persistence import Database
from umbod.infrastructure import (
    create_filesystem_browsing, create_filesystem_creation, create_filesystem_transactions,
    create_filesystem_uploads, create_filesystem_sharing,
)
from umbod.rest.authentication.local import LOCAL_DEVELOPMENT_ISSUER, local_rest_identity_enabled
from umbod.rest.authentication.authorization import JwtClaims
from umbod.rest.authentication.deps import get_caller_context, get_verified_access_claims
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories

from umbod.core.filesystem.uploads import SystemUploadClock, UploadClock, UploadService

from .errors import filesystem_errors


def get_filesystem_caller(
    caller: Annotated[CallerContext, Depends(get_caller_context)],
    claims: Annotated[JwtClaims, Depends(get_verified_access_claims)],
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
) -> CallerSnapshot:
    return CallerSnapshot(
        caller=caller,
        groups=group_membership_from_values((
            claims.claims.get(factories.settings.mcp.permission_group_claim),
        )),
    )


async def get_filesystem_database(
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
) -> Database:
    with filesystem_errors():
        await factories.persistence_runtime.readiness.ensure_ready()
        return factories.persistence_runtime.database


def get_filesystem_identity_resolver(
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
) -> FilesystemIdentityResolver:
    if local_rest_identity_enabled(factories.settings):
        return LocalDevelopmentIdentityResolver(Principal(
            type=PrincipalType.USER, issuer=LOCAL_DEVELOPMENT_ISSUER,
            id=factories.settings.admin_authentication.simulated_user_id,
        ))
    return VerifiedIdentityResolver()


async def require_filesystem_identity(
    caller: Annotated[CallerSnapshot, Depends(get_filesystem_caller)],
    resolver: Annotated[FilesystemIdentityResolver, Depends(get_filesystem_identity_resolver)],
) -> None:
    with filesystem_errors():
        if isinstance(await resolver.resolve(caller), UnresolvedIdentity):
            raise PermissionDenied()


def get_filesystem_browsing(
    database: Annotated[Database, Depends(get_filesystem_database)],
    resolver: Annotated[FilesystemIdentityResolver, Depends(get_filesystem_identity_resolver)],
) -> FilesystemBrowsing:
    return create_filesystem_browsing(database=database, resolver=resolver)


def get_filesystem_sharing(
    database: Annotated[Database, Depends(get_filesystem_database)],
    resolver: Annotated[FilesystemIdentityResolver, Depends(get_filesystem_identity_resolver)],
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
) -> FilesystemSharing:
    config = factories.settings
    issuer = filesystem_managed_issuer(config)
    with filesystem_errors():
        return create_filesystem_sharing(database=database, resolver=resolver, issuer=issuer)


def get_filesystem_upload_limit(
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
) -> int:
    return factories.settings.filesystem.upload_max_bytes


async def get_filesystem_content_driver(
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
) -> ContentDriver:
    with filesystem_errors():
        return factories.filesystem_content


def get_filesystem_content(
    database: Annotated[Database, Depends(get_filesystem_database)],
    resolver: Annotated[FilesystemIdentityResolver, Depends(get_filesystem_identity_resolver)],
    content: Annotated[ContentDriver, Depends(get_filesystem_content_driver)],
    max_bytes: Annotated[int, Depends(get_filesystem_upload_limit)],
) -> FilesystemContent:
    return ContentService(
        resolver, create_filesystem_transactions(database=database), content, max_bytes,
    )


def get_filesystem_upload_clock() -> UploadClock:
    return SystemUploadClock()


def get_filesystem_uploads(
    database: Annotated[Database, Depends(get_filesystem_database)],
    resolver: Annotated[FilesystemIdentityResolver, Depends(get_filesystem_identity_resolver)],
    content: Annotated[ContentDriver, Depends(get_filesystem_content_driver)],
    max_bytes: Annotated[int, Depends(get_filesystem_upload_limit)],
    clock: Annotated[UploadClock, Depends(get_filesystem_upload_clock)],
) -> UploadService:
    return create_filesystem_uploads(
        database=database, resolver=resolver, content=content, max_upload_bytes=max_bytes, clock=clock,
    )


def get_filesystem_deletion(
    database: Annotated[Database, Depends(get_filesystem_database)],
    resolver: Annotated[FilesystemIdentityResolver, Depends(get_filesystem_identity_resolver)],
) -> FilesystemDeletion:
    return DeletionService(resolver, create_filesystem_transactions(database=database))


def get_filesystem_creation(
    database: Annotated[Database, Depends(get_filesystem_database)],
    resolver: Annotated[FilesystemIdentityResolver, Depends(get_filesystem_identity_resolver)],
) -> FilesystemCreation:
    return create_filesystem_creation(database=database, resolver=resolver)
