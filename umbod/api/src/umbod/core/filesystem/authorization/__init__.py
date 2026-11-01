from .local_resolver import LocalDevelopmentIdentityResolver
from .errors import PermissionDenied
from .models import AuthorizationDecision, ResolvedIdentity, UnresolvedIdentity
from .discovery import (
    FILESYSTEM_DISCOVERY_CHANGED,
    AuthorizationGrant,
    AuthorizationNode,
    FilesystemAuthorizationSnapshot,
    FilesystemOperation,
    permitted_operations,
)
from .ports import FilesystemAuthorization, FilesystemAuthorizationReader, FilesystemIdentityResolver
from .service import AuthorizationService, allows_resolved
from .resolver import VerifiedIdentityResolver
from .recipients import ObservedUserPrincipalResolver

__all__ = [
    "FILESYSTEM_DISCOVERY_CHANGED",
    "AuthorizationGrant",
    "AuthorizationNode",
    "FilesystemAuthorizationSnapshot",
    "FilesystemAuthorizationReader",
    "FilesystemOperation",
    "permitted_operations",
    "AuthorizationDecision",
    "AuthorizationService",
    "allows_resolved",
    "VerifiedIdentityResolver",
    "ObservedUserPrincipalResolver",
    "LocalDevelopmentIdentityResolver",
    "FilesystemAuthorization",
    "FilesystemIdentityResolver",
    "PermissionDenied",
    "ResolvedIdentity",
    "UnresolvedIdentity",
]
