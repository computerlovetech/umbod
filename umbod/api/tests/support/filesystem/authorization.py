from dataclasses import dataclass
from typing import Union

from umbod.core.callers import (
    AuthenticationProvenance,
    CallerContext,
    DeclaredIssuer,
    SubjectIdentity,
)
from umbod.core.filesystem import AccessControlDriver, NamespaceDriver, Principal, PrincipalType
from umbod.core.filesystem.authorization import (
    AuthorizationService,
    FilesystemAuthorization,
    ResolvedIdentity,
    UnresolvedIdentity,
)


class SuppliedIdentityResolver:
    def __init__(self) -> None:
        self.identities: dict[CallerContext, Union[ResolvedIdentity, UnresolvedIdentity]] = {}

    async def resolve(
        self, caller: CallerContext
    ) -> Union[ResolvedIdentity, UnresolvedIdentity]:
        return self.identities.get(caller, UnresolvedIdentity())


def principal(
    identifier: str, principal_type: PrincipalType,
    issuer: str,
) -> Principal:
    return Principal(type=principal_type, issuer=issuer, id=identifier)


def caller(identifier: str) -> CallerContext:
    return CallerContext(
        authentication=AuthenticationProvenance.LOCAL_TEST,
        subject=SubjectIdentity(
            issuer=DeclaredIssuer(value="test-observations"), subject=identifier
        ),
    )


@dataclass(frozen=True)
class AuthorizationContext:
    authorization: FilesystemAuthorization
    resolver: SuppliedIdentityResolver
    namespace: NamespaceDriver
    policies: AccessControlDriver


def create_authorization_context(
    namespace: NamespaceDriver, policies: AccessControlDriver
) -> AuthorizationContext:
    resolver = SuppliedIdentityResolver()
    authorization: FilesystemAuthorization = AuthorizationService(
        resolver=resolver, namespace=namespace, access_control=policies
    )
    return AuthorizationContext(authorization, resolver, namespace, policies)
