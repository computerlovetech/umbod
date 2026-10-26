from typing import Annotated, NoReturn

from fastapi import Depends, HTTPException

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem.authorization import (
    FilesystemIdentityResolver,
    PermissionDenied,
    UnresolvedIdentity,
)

from ..deps import get_filesystem_caller, get_filesystem_identity_resolver
from ..errors import filesystem_errors


async def require_filesystem_identity(
    caller: Annotated[CallerSnapshot, Depends(get_filesystem_caller)],
    resolver: Annotated[FilesystemIdentityResolver, Depends(get_filesystem_identity_resolver)],
) -> None:
    with filesystem_errors():
        if isinstance(await resolver.resolve(caller), UnresolvedIdentity):
            raise PermissionDenied()


def not_implemented() -> NoReturn:
    raise HTTPException(
        501,
        detail={
            "code": "filesystem_not_implemented",
            "message": "Filesystem operation is not implemented.",
        },
        headers={"Cache-Control": "no-store"},
    )
