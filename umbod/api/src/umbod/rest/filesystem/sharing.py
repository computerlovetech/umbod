import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from umbod.core.callers import CallerSnapshot
from umbod.core.identity_directory.user_models import SearchText
from umbod.core.filesystem.sharing import (
    FilesystemSharing, NodePolicyView, ReplaceNodePolicy,
    ShareNodePolicy, SharingRecipientSearchQuery, SharingRecipientSearchResult,
    SharingRecipientType, SharingScope,
)

from umbod.core.filesystem.access import Visibility, RestrictedVisibility
from umbod.core.filesystem.authorization import PermissionDenied
from umbod.core.filesystem.browsing import FilesystemBrowsing

from .access import Access
from .deps import get_filesystem_caller, get_filesystem_sharing, get_filesystem_browsing
from .errors import filesystem_errors

router = APIRouter()
Caller = Annotated[CallerSnapshot, Depends(get_filesystem_caller)]
Sharing = Annotated[FilesystemSharing, Depends(get_filesystem_sharing)]
RECIPIENT_TYPE = TypeAdapter(SharingRecipientType)
RECIPIENT_QUERY = {
    "name": "recipient_type", "in": "query",
    "schema": {"type": "string", "enum": ["group", "user"]},
}


class NodePolicyWriteView(NodePolicyView):
    visible_to: Visibility


class ReplaceNodeAccessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    grants: tuple[ShareNodePolicy, ...]


def required_recipient_type(request: Request) -> SharingRecipientType:
    values = request.query_params.getlist("recipient_type")
    if len(values) == 1:
        try:
            return RECIPIENT_TYPE.validate_python(values[0])
        except ValidationError:
            pass
    raise HTTPException(422, detail=[{
        "loc": ["query", "recipient_type"], "type": "value_error",
        "msg": "Expected exactly one recipient_type: group or user.",
    }])


def sharing_scope(request: Request) -> SharingScope:
    if "recipient_type" not in request.query_params:
        return SharingScope(recipient_types=frozenset(("group", "user")))
    return SharingScope(recipient_types=frozenset((required_recipient_type(request),)))


def expected_sharing_revision(request: Request) -> str:
    values = request.headers.getlist("If-Match")
    if not values:
        raise HTTPException(428, detail={
            "code": "filesystem_precondition_required", "message": "If-Match is required.",
        })
    if (
        len(values) != 1
        or re.fullmatch(r'"[\x21\x23-\x2b\x2d-\x7e]+"', values[0]) is None
        or values[0][1:-1].isdigit()
    ):
        raise HTTPException(422, detail=[{
            "loc": ["header", "If-Match"], "type": "value_error",
            "msg": "Expected one strong quoted opaque sharing revision.",
        }])
    return values[0][1:-1]


@router.get(
    "/nodes/{node_id}/access/recipients", response_model=SharingRecipientSearchResult,
    openapi_extra={"parameters": [{
        **RECIPIENT_QUERY, "required": False,
        "description": "Filter recipients by type; omitted searches both types.",
    }]},
)
async def search_recipients(
    node_id: UUID, query: SearchText, caller: Caller, sharing: Sharing,
    scope: Annotated[SharingScope, Depends(sharing_scope)],
) -> SharingRecipientSearchResult:
    with filesystem_errors():
        return await sharing.search_recipients(
            caller, node_id, SharingRecipientSearchQuery(query=query, scope=scope),
        )


@router.get(
    "/nodes/{node_id}/access", response_model=NodePolicyView,
    openapi_extra={"parameters": [{
        **RECIPIENT_QUERY, "required": False,
        "description": "Filter the access view by recipient type; omitted returns both types.",
    }]},
)
async def inspect_access(
    node_id: UUID, caller: Caller, sharing: Sharing, response: Response,
    scope: Annotated[SharingScope, Depends(sharing_scope)],
) -> NodePolicyView:
    with filesystem_errors():
        view = await sharing.inspect(caller, node_id, scope)
    response.headers["ETag"] = f'"{view.revision}"'
    return view


@router.put(
    "/nodes/{node_id}/access", response_model=NodePolicyWriteView,
    openapi_extra={"parameters": [{
        **RECIPIENT_QUERY, "required": True,
        "description": "Replace only this recipient type; preserve all other and protected grants.",
    }, {
        "name": "If-Match", "in": "header", "required": True,
        "schema": {"type": "string"},
        "description": "One strong quoted opaque whole-policy revision, not a node content revision.",
    }]},
    responses={
        403: {"description": "Missing, undiscoverable or unauthorized node."},
        412: {"description": "Sharing revision no longer matches If-Match."},
        428: {"description": "If-Match is required."},
    },
)
async def replace_access(
    node_id: UUID, body: ReplaceNodeAccessRequest, caller: Caller, sharing: Sharing,
    response: Response, revision: Annotated[str, Depends(expected_sharing_revision)],
    recipient_type: Annotated[SharingRecipientType, Depends(required_recipient_type)],
    access: Access, browsing: Annotated[FilesystemBrowsing, Depends(get_filesystem_browsing)],
) -> NodePolicyWriteView:
    try:
        command = ReplaceNodePolicy(
            expected_revision=revision, recipient_type=recipient_type, grants=body.grants,
        )
    except ValidationError:
        raise HTTPException(422, detail=[{
            "loc": ["body", "grants"], "type": "value_error",
            "msg": "Recipients must be unique and match recipient_type.",
        }]) from None
    with filesystem_errors():
        view = await sharing.replace(caller, node_id, command)
        try:
            node = await browsing.get_node(caller, node_id)
            visible_to = (await access.enrich_nodes(caller, [node]))[0].visible_to
        except PermissionDenied:
            visible_to = RestrictedVisibility(type="restricted")
        view = NodePolicyWriteView(**view.model_dump(), visible_to=visible_to)
    response.headers["ETag"] = f'"{view.revision}"'
    return view
