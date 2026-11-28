import os
import ssl
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastmcp import Client

from conftest import RuntimeEndpoints
from test_running_personal_mcp_execution import checked, mcp_client, proxy_token

_SETTINGS = "/api/admin/system-settings/portable-connectors"
_CATALOG = "/api/admin/portable-connectors"
_CREATE = "portable_connector_create_draft"
_SAVE = "portable_connector_save_revision"
_VALIDATE = "portable_connector_validate_revision"
_SUBMIT = "portable_connector_submit_revision"
_DRAFT_TOOLS = {_CREATE, _SAVE, _VALIDATE}
_FIXTURE_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "tests/umbod/infrastructure/portable_connectors/fixtures"
)
_SOURCE_FIXTURE = _FIXTURE_DIRECTORY / "issue_tracker.py"
_CONFIGURATION_PROBE = _FIXTURE_DIRECTORY / "configuration_probe.py"


async def listed_draft_tools(client: Client[Any]) -> set[str]:
    return {tool.name for tool in await client.list_tools()} & _DRAFT_TOOLS


async def assert_cached_create_denied(client: Client[Any]) -> None:
    result = await client.call_tool(_CREATE, {"source": "def invalid(:\n"}, raise_on_error=False)
    assert result.is_error
    assert not result.structured_content


@pytest.mark.asyncio
async def test_portable_drafts_follow_admin_setting_without_reconnecting(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    member_token = os.environ.get("UMBOD_TEST_MEMBER_BEARER_TOKEN")
    if not member_token:
        pytest.skip("Requires the runner's signed personal-runtime phase")
    tls = ssl.create_default_context(cafile=os.environ["UMBOD_TEST_PERSONAL_CA"])
    with (
        httpx.Client(
            base_url=runtime_endpoints.api_base_url,
            headers={"Authorization": f"Bearer {runtime_endpoints.bearer_token}"},
            timeout=30,
        ) as admin,
        httpx.Client(base_url=os.environ["UMBOD_TEST_PERSONAL_URL"], verify=tls, timeout=30) as identity,
    ):
        assert checked(admin.get(_SETTINGS)) == {"enabled": False}
        mcp_url = runtime_endpoints.mcp_url
        async with mcp_client(mcp_url, proxy_token(mcp_url, member_token, identity)) as author:
            assert await listed_draft_tools(author) == set()
            await assert_cached_create_denied(author)
            try:
                assert checked(admin.patch(_SETTINGS, json={"enabled": True})) == {"enabled": True}
                assert await listed_draft_tools(author) == _DRAFT_TOOLS

                created = await author.call_tool(_CREATE, {"source": "def invalid(:\n"})
                assert not created.is_error
                assert created.structured_content is not None
                draft_id = created.structured_content["draft_id"]
                original = created.structured_content["revision_id"]

                saved = await author.call_tool(_SAVE, {
                    "draft_id": draft_id,
                    "expected_revision_id": original,
                    "source": _SOURCE_FIXTURE.read_text(encoding="utf-8"),
                })
                assert not saved.is_error
                assert saved.structured_content is not None
                replacement = saved.structured_content["revision_id"]
                assert replacement != original

                for revision_id, status in ((original, "invalid"), (replacement, "valid")):
                    validated = await author.call_tool(_VALIDATE, {
                        "draft_id": draft_id, "revision_id": revision_id,
                    })
                    assert not validated.is_error
                    report = validated.structured_content
                    assert report is not None
                    assert report["revision_id"] == revision_id
                    assert report["status"] == status
                    assert report["checks"]["handler_execution"] == "not_checked"
            finally:
                assert checked(admin.patch(_SETTINGS, json={"enabled": False})) == {"enabled": False}

            assert await listed_draft_tools(author) == set()
            await assert_cached_create_denied(author)


@pytest.mark.asyncio
async def test_admin_can_configure_submitted_portable_connector_after_disabling_mcp_creation(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    member_token = os.environ.get("UMBOD_TEST_MEMBER_BEARER_TOKEN")
    if not member_token:
        pytest.skip("Requires the runner's signed personal-runtime phase")
    tls = ssl.create_default_context(cafile=os.environ["UMBOD_TEST_PERSONAL_CA"])
    admin_token = runtime_endpoints.bearer_token
    mcp_url = runtime_endpoints.mcp_url
    source = _CONFIGURATION_PROBE.read_text(encoding="utf-8")
    with (
        httpx.Client(
            base_url=runtime_endpoints.api_base_url,
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30,
        ) as admin_api,
        httpx.Client(base_url=os.environ["UMBOD_TEST_PERSONAL_URL"], verify=tls, timeout=30) as identity,
    ):
        async with (
            mcp_client(mcp_url, proxy_token(mcp_url, admin_token, identity)) as admin,
            mcp_client(mcp_url, proxy_token(mcp_url, member_token, identity)) as member,
        ):
            assert checked(admin_api.get(_SETTINGS)) == {"enabled": False}
            assert _SUBMIT not in {tool.name for tool in await admin.list_tools()}
            try:
                assert checked(admin_api.patch(_SETTINGS, json={"enabled": True})) == {"enabled": True}
                assert _SUBMIT in {tool.name for tool in await admin.list_tools()}
                assert _SUBMIT not in {tool.name for tool in await member.list_tools()}
                member_draft = await member.call_tool(_CREATE, {"source": source})
                assert member_draft.structured_content is not None
                member_revision = {key: member_draft.structured_content[key] for key in ("draft_id", "revision_id")}
                for caller in (member, admin):
                    denied = await caller.call_tool(_SUBMIT, member_revision, raise_on_error=False)
                    assert denied.is_error and denied.structured_content is None

                draft = await admin.call_tool(_CREATE, {"source": source})
                assert draft.structured_content is not None
                revision = {key: draft.structured_content[key] for key in ("draft_id", "revision_id")}
                submitted = await admin.call_tool(_SUBMIT, revision)
                assert submitted.structured_content is not None
                assert submitted.structured_content["status"] == "inactive"
                assert submitted.structured_content["revision_id"] == revision["revision_id"]
                connector_id = submitted.structured_content["connector_id"]
                assert connector_id
                repeated = await admin.call_tool(_SUBMIT, revision)
                assert repeated.structured_content == submitted.structured_content
            finally:
                assert checked(admin_api.patch(_SETTINGS, json={"enabled": False})) == {"enabled": False}

            names = {tool.name for tool in await admin.list_tools()}
            assert _SUBMIT not in names
            assert not any(name.startswith("configuration_probe") for name in names)
            denied = await admin.call_tool(_SUBMIT, revision, raise_on_error=False)
            assert denied.is_error and denied.structured_content is None

            summary = next(
                entry for entry in checked(admin_api.get(_CATALOG))["connectors"]
                if entry["connector_id"] == connector_id
            )
            assert summary["name"] == "Configuration probe"
            assert summary["status"] == "inactive"
            assert summary["configured"] is False
            configuration_url = f"{_CATALOG}/{connector_id}/configuration"
            detail = checked(admin_api.get(configuration_url))
            assert detail["connector"] == summary
            assert detail["configuration"] is None
            fields = {field["name"]: field for field in detail["fields"]}
            assert fields["workspace"]["label"] == "Workspace"
            assert fields["workspace"]["required"] is True
            assert fields["mode"]["choices"] == ["preview", "review"]

            configuration = {"workspace": "kind-probe", "mode": "preview"}
            saved = checked(admin_api.put(configuration_url, json={"configuration": configuration}))
            assert saved["configuration"] == configuration
            assert saved["connector"]["configured"] is True
            assert saved["connector"]["status"] == "inactive"
            assert checked(admin_api.get(configuration_url)) == saved
            assert not any(tool.name.startswith("configuration_probe") for tool in await admin.list_tools())
