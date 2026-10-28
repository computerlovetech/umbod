from typing import NoReturn

from fastapi import HTTPException


def not_implemented() -> NoReturn:
    raise HTTPException(
        501,
        detail={
            "code": "filesystem_not_implemented",
            "message": "Filesystem operation is not implemented.",
        },
        headers={"Cache-Control": "no-store"},
    )
