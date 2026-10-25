import asyncio
from contextvars import ContextVar
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastmcp.server.auth import AccessToken

from umbod.mcp.connectors.openapi import OpenApiCodeModeExecutionAdapter
from umbod.mcp.connectors.openapi import deps
from umbod.mcp.connectors.native.tools.deployment_modes.codemode import OpenApiCodeModeInvocation


@pytest.mark.parametrize("raw,expected", [
    ([" team ", "", 1, "alpha", "alpha"], (" team ", "alpha")),
    (" ", (" ",)), ("", ()), ({"alpha": True}, ()), (None, ()),
])
def test_capture_openapi_groups_preserves_filtering_and_order(
    monkeypatch: pytest.MonkeyPatch, raw: object, expected: tuple[str, ...],
) -> None:
    token = AccessToken(token="secret", client_id="client", scopes=[], claims={"groups": raw})
    monkeypatch.setattr(deps, "get_access_token", lambda: token)

    groups = deps.capture_openapi_groups(SimpleNamespace(permission_group_claim="groups"))
    token.claims["groups"] = ["replacement"]

    assert groups.group_ids == expected


def test_capture_openapi_groups_without_sdk_token_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deps, "get_access_token", lambda: None)

    assert deps.capture_openapi_groups(SimpleNamespace(permission_group_claim="groups")).group_ids == ()


@pytest.mark.asyncio
async def test_retained_executor_captures_groups_before_awaits_and_isolates_overlapping_callers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current: ContextVar[AccessToken] = ContextVar("openapi_test_token")
    monkeypatch.setattr(deps, "get_access_token", current.get)
    observed: dict[str, tuple[str, ...]] = {}

    async def create_store() -> SimpleNamespace:
        current.get().claims["groups"] = ["changed-after-capture"]
        await asyncio.sleep(0)
        return SimpleNamespace(get_connector=AsyncMock(return_value=SimpleNamespace(display_name="API")))

    async def execute(operation: object, groups: tuple[str, ...]) -> SimpleNamespace:
        observed[operation.operation_id] = groups
        return SimpleNamespace(model_dump=lambda mode: {})

    async def execution_service(*args: object) -> SimpleNamespace:
        return SimpleNamespace(execute=execute)

    monkeypatch.setattr(OpenApiCodeModeExecutionAdapter, "_execution_service", execution_service)
    server = SimpleNamespace(
        permission_group_claim="groups",
        openapi_connector_store_factory=SimpleNamespace(create=create_store),
        group_permission_reader_factory=SimpleNamespace(create=AsyncMock(return_value=object())),
        openapi_outbound_http_client_factory=SimpleNamespace(create=object),
        connector_invocation_policy=object(),
        metrics_recorder=object(),
    )
    adapter = OpenApiCodeModeExecutionAdapter(server, object())

    async def invoke(caller: str) -> None:
        current.set(AccessToken(token=caller, client_id="client", scopes=[], claims={"groups": [caller]}))
        await adapter.execute(OpenApiCodeModeInvocation(
            connector_id="api", operation_id=caller, path={}, query={}, headers={}, body={},
        ))

    await invoke("first")
    await asyncio.gather(invoke("alice"), invoke("bob"))

    assert observed == {"first": ("first",), "alice": ("alice",), "bob": ("bob",)}
