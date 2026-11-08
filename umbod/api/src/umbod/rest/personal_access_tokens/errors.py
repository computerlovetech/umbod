from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import HTTPException

from umbod.core.personal_access_tokens import UntrustedPersonalAccessTokenCaller


@asynccontextmanager
async def token_operation() -> AsyncIterator[None]:
    try:
        yield
    except UntrustedPersonalAccessTokenCaller:
        raise HTTPException(
            status_code=403, detail="Verified identity required"
        ) from None
    except Exception:
        raise HTTPException(
            status_code=503, detail="Personal access token service unavailable"
        ) from None
