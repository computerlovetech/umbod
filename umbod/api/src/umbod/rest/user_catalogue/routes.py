from typing import Annotated

from fastapi import APIRouter, Depends, Response

from umbod.core.user_catalogue import UserCatalogue, UserCatalogueReader

from .dependencies import get_user_catalogue

router = APIRouter(tags=["user-catalogue"])


@router.get("/catalogue", response_model=UserCatalogue)
async def read_catalogue(
    response: Response,
    catalogue: Annotated[UserCatalogueReader, Depends(get_user_catalogue)],
) -> UserCatalogue:
    response.headers["Cache-Control"] = "no-store"
    return await catalogue.read()
