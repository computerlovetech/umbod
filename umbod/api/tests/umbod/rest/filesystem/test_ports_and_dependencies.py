from typing import Annotated
from unittest.mock import Mock, create_autospec
from uuid import UUID, uuid4

import pytest
from fastapi import Depends, Request

from umbod.core.callers import AuthenticationProvenance, CallerContext, CallerSnapshot, DeclaredIssuer, SubjectIdentity
from umbod.core.filesystem import FilesystemCreation, InvalidName, NameCollision, NodeMetadata, StorageFailure, WrongNodeKind
from umbod.core.filesystem.authorization import PermissionDenied
from umbod.core.filesystem.browsing import FilesystemBrowsing
from umbod.core.filesystem.content import FilesystemContent
from umbod.rest.authentication.authorization import JwtClaims
from umbod.rest.authentication.deps import get_caller_context, get_verified_access_claims
from umbod.rest.filesystem import deps

from .conftest import FilesystemHttp
from .test_http_contract import BASE, BODY, creation_payload

OPERATIONS = [
    ("GET", "/root", "get_root"),
    ("GET", "/nodes/{id}", "get_node"),
    ("GET", "/nodes/{id}/children", "list_children"),
    ("POST", "/nodes/{id}/files", "upload"),
    ("POST", "/nodes/{id}/directories", "create_directory"),
]


@pytest.mark.parametrize("method,path,operation", OPERATIONS)
@pytest.mark.parametrize("error,status,code,message", [
    (PermissionDenied, 403, "filesystem_permission_denied", "Filesystem access denied."),
    (InvalidName, 422, "filesystem_invalid_name", "Invalid filesystem name."),
    (NameCollision, 409, "filesystem_name_collision", "Filesystem name already exists."),
    (WrongNodeKind, 409, "filesystem_wrong_node_kind", "Invalid filesystem node kind."),
    (StorageFailure, 500, "filesystem_storage_failure", "Filesystem operation failed."),
])
def test_port_delegation_and_fixed_error_translation(
    filesystem_http: FilesystemHttp, method: str, path: str, operation: str,
    error: type[Exception], status: int, code: str, message: str,
) -> None:
    browsing = create_autospec(FilesystemBrowsing, instance=True)
    creation = create_autospec(FilesystemCreation, instance=True)
    content = create_autospec(FilesystemContent, instance=True)
    service = content if operation == "upload" else creation if method == "POST" else browsing
    getattr(service, operation).side_effect = error("secret storage/key owner credential")

    def provide_browsing() -> FilesystemBrowsing:
        return browsing

    def provide_creation() -> FilesystemCreation:
        return creation

    def provide_content() -> FilesystemContent:
        return content

    filesystem_http.app.dependency_overrides[deps.get_filesystem_content] = provide_content
    filesystem_http.app.dependency_overrides[deps.get_filesystem_browsing] = provide_browsing
    filesystem_http.app.dependency_overrides[deps.get_filesystem_creation] = provide_creation
    identifier = uuid4()
    response = filesystem_http.client.request(
        method, BASE + path.format(id=identifier),
        **creation_payload("files" if operation == "upload" else "directories", BODY),
    )
    assert response.status_code == status
    assert response.json() == {"detail": {"code": code, "message": message}}
    assert response.headers["cache-control"] == "no-store"
    arguments = getattr(service, operation).await_args.args
    assert isinstance(arguments[0], CallerSnapshot)
    assert arguments[0].groups.group_ids == ("team",)
    assert arguments[0].caller.subject == SubjectIdentity(issuer=DeclaredIssuer(value="issuer"), subject="alice")
    if operation != "get_root":
        assert arguments[1] == identifier and isinstance(arguments[1], UUID)
    if method == "POST":
        assert arguments[2:4] == ("child", NodeMetadata.model_validate(BODY["metadata"]))
    if operation == "upload":
        content.authorize_upload.assert_awaited_once_with(arguments[0], identifier)
        assert len(arguments) == 5


def test_capture_reuses_accepted_state_once_and_never_promotes_provenance(filesystem_http: FilesystemHttp) -> None:
    app = filesystem_http.app
    del app.dependency_overrides[get_caller_context]
    contexts: list[CallerContext] = []
    claims: list[JwtClaims] = []

    def observe_context(request: Request) -> CallerContext:
        context = get_caller_context(request)
        contexts.append(context)
        return context

    def observe_claims(request: Request) -> JwtClaims:
        accepted = get_verified_access_claims(request)
        claims.append(accepted)
        return accepted

    def probe(
        first: Annotated[CallerSnapshot, Depends(deps.get_filesystem_caller)],
        second: Annotated[CallerSnapshot, Depends(deps.get_filesystem_caller)],
    ) -> CallerSnapshot:
        assert first is second
        assert first.caller is contexts[-1]
        return first

    app.dependency_overrides[get_caller_context] = observe_context
    app.dependency_overrides[get_verified_access_claims] = observe_claims
    app.add_api_route("/capture", probe, methods=["GET"])
    for subject in ("alice", "bob", "alice"):
        response = filesystem_http.client.get("/api/me/capture", headers={"Authorization": f"Bearer {subject}"})
        captured = CallerSnapshot.model_validate(response.json())
        assert captured.caller.authentication == AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED
        assert captured.caller.subject.subject == subject
        assert captured.groups.group_ids == ("team",)
    assert len(contexts) == len(claims) == 3
    assert contexts[0] is not contexts[1]


@pytest.mark.parametrize("groups,expected", [
    (" exact ", (" exact ",)), (("team", "", "team", 4, " other "), ("team", "", " other ")),
    ({"first": 1, "second": 2}, ("first", "second")), (None, ()),
])
def test_capture_preserves_shared_group_projection(
    filesystem_http: FilesystemHttp, groups: object, expected: tuple[str, ...],
) -> None:
    claims = JwtClaims(claims={"filesystem_groups": groups, "groups": ["wrong"]})
    request = Request({"type": "http", "state": {"caller_context": CallerContext(
        authentication=AuthenticationProvenance.LOCAL_TEST,
        subject=SubjectIdentity(issuer=DeclaredIssuer(value="issuer"), subject="alice"),
    ), "verified_access_claims": claims}})
    captured = deps.get_filesystem_caller(
        get_caller_context(request), get_verified_access_claims(request), filesystem_http.factories,
    )
    assert captured.groups.group_ids == expected
    assert captured.caller.authentication == AuthenticationProvenance.LOCAL_TEST


@pytest.mark.parametrize("provenance", [AuthenticationProvenance.LOCAL_TEST, AuthenticationProvenance.UNAVAILABLE])
def test_unresolved_identity_is_denied_without_promotion(
    filesystem_http: FilesystemHttp, provenance: AuthenticationProvenance,
) -> None:
    def unresolved(request: Request) -> CallerContext:
        context = get_caller_context(request)
        if provenance == AuthenticationProvenance.UNAVAILABLE:
            return CallerContext(authentication=provenance, subject={"kind": "unavailable"})
        return context.model_copy(update={"authentication": provenance})

    filesystem_http.app.dependency_overrides[get_caller_context] = unresolved
    response = filesystem_http.client.get(f"{BASE}/root")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "filesystem_permission_denied"


def test_services_are_request_local_and_use_prepared_runtime(
    filesystem_http: FilesystemHttp, monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_factory = deps.create_filesystem_browsing
    factory = Mock(side_effect=real_factory)
    monkeypatch.setattr(deps, "create_filesystem_browsing", factory)
    for _ in range(2):
        assert filesystem_http.client.get(f"{BASE}/root").status_code == 200
    assert factory.call_count == 2
    first, second = factory.call_args_list
    assert first.kwargs["database"] is second.kwargs["database"] is filesystem_http.factories.persistence_runtime.database
    assert first.kwargs["resolver"] is not second.kwargs["resolver"]
