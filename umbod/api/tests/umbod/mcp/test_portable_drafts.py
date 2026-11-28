from asyncio import Event, TaskGroup, wait, wait_for
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from hashlib import sha256
from json import loads
from pathlib import Path
from typing import Any, Literal
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx2
import pytest
from fastmcp import Client
from fastmcp.client.client import CallToolResult
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from starlette.applications import Starlette

from tests.persistence_runtime import prepared_inmemory_runtime
from tests.support.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.config.system_settings import ConfiguredSystemSettingsDefaults
from umbod.core.connectors.downstream_mcp.models import NoAuthConnectorDefinition
from umbod.core.connectors.downstream_mcp.stores import CONNECTOR_DEFINITION_TABLE, ConnectorDefinitionStoreService, SaveConnectorDefinition
from umbod.core.connectors.native.runtime import ConnectorRuntime
from umbod.core.connectors.portable.draft_validation import DraftValidationReport, DraftValidationUnavailable, PortableDraftValidation
from umbod.core.connectors.portable.drafts import DatabaseDraftStore, DraftRevision, DraftWriteUnconfirmed
from umbod.core.connectors.portable.drafts.models import DraftAuthor
from umbod.core.connectors.portable.managed import DatabaseManagedConnectorStore, ManagedSubmissionWriteUnconfirmed
from umbod.core.connectors.portable.managed.models import ManagedConnectorReceipt, PortableConnectorSubmission
from umbod.core.connectors.portable.managed.schema import MANAGED_CONNECTOR_TABLE, ManagedConnectorRow
from umbod.core.persistence import AllFields, Database, NoFilter, Query, Unordered
from umbod.core.publishing.factories import create_connector_publishing_store
from umbod.core.system_settings import SystemSettingsService, create_system_settings_service_with_defaults
from umbod.core.system_settings.models import UpdatePortableConnectorSettings
from umbod.mcp.agent_behaviour.reservations import connector_tool_name_available
from umbod.mcp.context import PublicAppConfig
from umbod.mcp.logging.invocation.formatting import StructuredMcpToolInvocationLogFormatter
from umbod.mcp.logging.invocation.sink import InMemoryMcpToolInvocationLogSink
from umbod.mcp.public_app import build_starlette_app, create_runtime_context
from umbod.mcp.runtime_adapters import create_configured_downstream_client_factory, create_configured_openapi_runtime_adapters
from umbod.mcp.runtime_options import ConnectorRuntimeSourceStores, StoreBackedConnectorRuntimeStateSourceStrategy
from umbod.mcp.settings import MCPAppSettings, MCPSettings
from umbod.mcp.telemetry.composition import create_configured_mcp_telemetry

pytestmark = pytest.mark.asyncio

_CREATE = "portable_connector_create_draft"
_SAVE = "portable_connector_save_revision"
_VALIDATE = "portable_connector_validate_revision"
_SUBMIT = "portable_connector_submit_revision"
_NAMES = {_CREATE, _SAVE, _VALIDATE}
_ISSUER = "https://private-identity.example"
_AUTHOR = "private-author-subject"
_CLIENT_ID = "private-agent-client"
_PRIVATE_SOURCE = "private-source-marker"
_PROXY_PATH = "/mcp/proxies/portable-draft-scope-test"
_FIXTURE_DIRECTORY = Path(__file__).resolve().parents[1] / "infrastructure/portable_connectors/fixtures"
_FIXTURE = _FIXTURE_DIRECTORY / "issue_tracker.py"
_SUBMISSION_FIXTURE = _FIXTURE_DIRECTORY / "configuration_probe.py"


@dataclass(frozen=True)
class _Harness:
    app: Starlette
    settings: SystemSettingsService
    logs: InMemoryMcpToolInvocationLogSink
    database: Database

    async def managed_records(self) -> list[ManagedConnectorRow]:
        async with self.database.read_session() as session:
            return list(await session.find_many(MANAGED_CONNECTOR_TABLE, Query(NoFilter(), AllFields(), Unordered())))

    async def set_enabled(self, enabled: bool) -> None:
        await self.settings.set_portable_connectors_enabled(
            "administrator", UpdatePortableConnectorSettings(portable_connectors_enabled=enabled),
        )

    def connect(self, token: str, path: str = "/mcp") -> Client:
        def create_http_client(**kwargs: Any) -> httpx2.AsyncClient:
            return httpx2.AsyncClient(transport=httpx2.ASGITransport(app=self.app), **kwargs)

        transport = StreamableHttpTransport(
            f"http://localhost{path}", headers={"Authorization": f"Bearer {token}"},
            httpx_client_factory=create_http_client,
        )
        return Client(transport, timeout=12, mode="legacy")


def _token_claims(issuer: str, subject: str) -> dict[str, Any]:
    return {"client_id": _CLIENT_ID, "scopes": [], "iss": issuer, "sub": subject}


def _unrelated_tool() -> str:
    return "available"


@asynccontextmanager
async def _harness(
    mode: Literal["flat", "gateway", "codemode"], *, google: GoogleProvider | None = None,
) -> AsyncIterator[_Harness]:
    persistence = await prepared_inmemory_runtime()
    settings = MCPAppSettings(
        mcp=MCPSettings(connector_tool_exposure_mode=mode, metrics_enabled=False, downstream_discovery_enabled=False, _env_file=None),
        _env_file=None,
    )
    logs = InMemoryMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter())
    verifier = StaticTokenVerifier(tokens={
        "author": {**_token_claims(_ISSUER, _AUTHOR), "role": "administrator"},
        "admin": {**_token_claims(_ISSUER, _AUTHOR), "groups": ["umbod-admins"]},
        "other_admin": {**_token_claims(_ISSUER, "other-administrator"), "groups": ["umbod-admins"]},
        "other_issuer": _token_claims("https://other-identity.example", _AUTHOR),
        "other_subject": _token_claims(_ISSUER, "other-subject"),
        "missing_issuer": {"client_id": _CLIENT_ID, "scopes": [], "sub": _AUTHOR},
    })
    publishing = await create_connector_publishing_store(persistence.database)
    runtime = ConnectorRuntime(
        connector_registrations=[], connector_tool_mappings=[],
        connector_configuration_store=InMemoryConnectorCurrentConfigurationStore(),
        connector_publishing_store=publishing,
    )
    config = PublicAppConfig(
        settings=settings, connector_runtime=runtime, source_stores=ConnectorRuntimeSourceStores(),
        configured_source_strategy=StoreBackedConnectorRuntimeStateSourceStrategy(), stateless_http=False,
        api_base_url=None, persistence_runtime=persistence, auth_provider=google if google is not None else verifier,
        telemetry=replace(create_configured_mcp_telemetry(settings), invocation_log_sink=logs),
    )
    try:
        await ConnectorDefinitionStoreService(persistence.database, CONNECTOR_DEFINITION_TABLE).save(
            SaveConnectorDefinition(definition=NoAuthConnectorDefinition(
                connector_id="scope-test", display_name="Scope test", tool_name_prefix="scope_test",
                endpoint_url="https://scope.example.test/mcp", public_path=_PROXY_PATH,
            )),
        )
        await publishing.publish_connector("scope-test")
        context = await create_runtime_context(
            config, downstream_client_factory=await create_configured_downstream_client_factory(settings, persistence.database),
            openapi_adapters=create_configured_openapi_runtime_adapters(settings),
        )
        context.mcp.tool(_unrelated_tool, name="unrelated_tool")
        app = await build_starlette_app(context)
        service = create_system_settings_service_with_defaults(persistence.database, defaults=ConfiguredSystemSettingsDefaults(settings))
        async with app.router.lifespan_context(app):
            yield _Harness(app, service, logs, persistence.database)
    finally:
        await persistence.shutdown()


def _payload(result: CallToolResult) -> dict[str, Any]:
    assert not result.is_error
    assert result.structured_content is not None
    return result.structured_content


def _failure(result: CallToolResult) -> dict[str, Any]:
    assert result.is_error and result.structured_content is None
    assert result.meta is not None
    return result.meta["computerlove.tech/umbod"]["guidance"]


@pytest.mark.parametrize("mode", ["flat", "gateway", "codemode"])
async def test_same_authenticated_session_observes_portable_drafts_toggle(
    mode: Literal["flat", "gateway", "codemode"],
) -> None:
    async with _harness(mode) as harness, harness.connect("author") as client:
        session_id = client.transport.get_session_id()
        assert session_id is not None
        baseline = {tool.name for tool in await client.list_tools()}
        assert not _NAMES.intersection(baseline)
        assert "unrelated_tool" in baseline
        arguments = {"source": "def broken(:\n"}
        assert (await client.call_tool(_CREATE, arguments, raise_on_error=False)).is_error

        await harness.set_enabled(True)
        tools = {tool.name: tool for tool in await client.list_tools()}
        assert tools.keys() == baseline | _NAMES
        required_fields = {_CREATE: {"source"}, _SAVE: {"source", "draft_id", "expected_revision_id"}, _VALIDATE: {"draft_id", "revision_id"}}
        for name, fields in required_fields.items():
            schema = tools[name].input_schema
            assert set(schema["required"]) == fields == schema["properties"].keys()
            assert not schema["additionalProperties"]
            for field in fields - {"source"}:
                assert schema["properties"][field]["format"] == "uuid"
        assert tools[_CREATE].input_schema["properties"]["source"]["maxLength"] == 65536
        if mode != "flat":
            search = await client.call_tool("search_tools", {"query": "portable connector create draft"})
            assert all(name not in repr(search.content) for name in _NAMES)
        assert "UTF-8" in (tools[_CREATE].description or "")
        assert "expected_revision_id" in (tools[_SAVE].description or "")
        receipt = _payload(await client.call_tool(_CREATE, arguments))
        assert receipt["source_sha256"] == sha256(arguments["source"].encode()).hexdigest()
        draft = {"draft_id": receipt["draft_id"], "revision_id": receipt["revision_id"]}

        await harness.set_enabled(False)
        assert {tool.name for tool in await client.list_tools()} == baseline
        for name, cached in ((_CREATE, arguments), (_SAVE, {**arguments, "draft_id": draft["draft_id"], "expected_revision_id": draft["revision_id"]}), (_VALIDATE, draft)):
            assert (await client.call_tool(name, cached, raise_on_error=False)).is_error
        assert not (await client.call_tool("unrelated_tool", {})).is_error
        assert client.transport.get_session_id() == session_id


async def test_exact_revision_validation_is_offline_and_does_not_expose_source_or_actor() -> None:
    source = _FIXTURE.read_text(encoding="utf-8")
    async with _harness("flat") as harness, harness.connect("author") as client:
        await harness.set_enabled(True)
        private = f"# {_PRIVATE_SOURCE}\r\nimport requests\r\n"
        original = _payload(await client.call_tool(_CREATE, {"source": private}))
        assert original["source_sha256"] == sha256(private.encode()).hexdigest()
        command = {"source": source, "draft_id": original["draft_id"], "expected_revision_id": original["revision_id"]}
        corrected = _payload(await client.call_tool(_SAVE, command))
        stale = await client.call_tool(_SAVE, command, raise_on_error=False)
        assert _failure(stale)["error"]["code"] == "draft_head_changed"

        original_result = await client.call_tool(_VALIDATE, {"draft_id": original["draft_id"], "revision_id": original["revision_id"]})
        invalid = _payload(original_result)
        assert invalid["revision_id"] == original["revision_id"]
        assert invalid["status"] == "invalid"
        assert invalid["diagnostics"][0]["code"] == "import_unavailable"
        assert invalid["diagnostics"][0]["line"] == 2
        assert "HttpContext" in repr(original_result.content)
        assert _PRIVATE_SOURCE not in repr(original_result)

        validated = _payload(await client.call_tool(_VALIDATE, {"draft_id": corrected["draft_id"], "revision_id": corrected["revision_id"]}))
        assert validated["revision_id"] == corrected["revision_id"]
        assert validated["status"] == "valid"
        assert validated["checks"] == {"load": "passed", "manifest": "passed", "handler_imports": "passed", "handler_execution": "not_checked"}
        assert all("issue_tracker" not in tool.name for tool in await client.list_tools())

        private_records = [record for record in harness.logs.invocation_records() if record.attributes.get("mcp.tool.name") in _NAMES]
        assert len(private_records) == 5
        for forbidden in (_ISSUER, _AUTHOR, _CLIENT_ID, client.transport.get_session_id(), _PRIVATE_SOURCE, original["draft_id"], original["revision_id"], corrected["revision_id"]):
            assert forbidden not in repr(private_records)


@pytest.mark.parametrize("token", ["other_issuer", "other_subject"])
async def test_draft_is_private_to_exact_issuer_and_subject(token: str) -> None:
    async with _harness("flat") as harness, harness.connect("author") as owner, harness.connect(token) as stranger:
        await harness.set_enabled(True)
        receipt = _payload(await owner.call_tool(_CREATE, {"source": "not_a_connector = True"}))
        command = {"draft_id": receipt["draft_id"], "revision_id": receipt["revision_id"]}
        inaccessible = _failure(await stranger.call_tool(_VALIDATE, command, raise_on_error=False))
        missing = _failure(await stranger.call_tool(_VALIDATE, {**command, "draft_id": str(uuid4())}, raise_on_error=False))
        assert inaccessible == missing
        denied_save = await stranger.call_tool(_SAVE, {"draft_id": receipt["draft_id"], "expected_revision_id": receipt["revision_id"], "source": "0"}, raise_on_error=False)
        assert _failure(denied_save) == missing


async def test_enabled_drafts_remain_unavailable_without_a_verified_issuer() -> None:
    async with _harness("flat") as harness, harness.connect("missing_issuer") as client:
        await harness.set_enabled(True)
        assert not _NAMES.intersection(tool.name for tool in await client.list_tools())
        assert (await client.call_tool(_CREATE, {"source": "1"}, raise_on_error=False)).is_error


async def test_google_verified_subject_can_author_without_an_issuer_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = GoogleProvider(
        client_id=_CLIENT_ID, client_secret="unused", base_url="http://localhost",
        jwt_signing_key="portable-drafts-test-signing-key",
    )
    verify = AsyncMock(return_value=AccessToken(
        token="author", client_id=_CLIENT_ID, scopes=provider.required_scopes, claims={"sub": _AUTHOR},
    ))
    monkeypatch.setattr(provider, "verify_token", verify)
    async with _harness("flat", google=provider) as harness, harness.connect("author") as client:
        await harness.set_enabled(True)
        assert _NAMES <= {tool.name for tool in await client.list_tools()}
        receipt = _payload(await client.call_tool(_CREATE, {"source": "1"}))
        assert receipt["draft_id"]
        assert verify.await_count > 0


@pytest.mark.parametrize(
    ("arguments", "expected_code"),
    [
        ({"source": "   "}, "invalid_draft_source"),
        ({"source": "🙂" * 16385}, "invalid_draft_source"),
        ({"source": "0", _PRIVATE_SOURCE: _PRIVATE_SOURCE}, "invalid_arguments"),
    ],
)
async def test_create_rejects_bad_arguments_without_echoing_values(
    arguments: dict[str, str], expected_code: str,
) -> None:
    async with _harness("flat") as harness, harness.connect("author") as client:
        await harness.set_enabled(True)
        result = await client.call_tool(_CREATE, arguments, raise_on_error=False)
        assert _failure(result)["error"]["code"] == expected_code
        assert _PRIVATE_SOURCE not in repr(result)


async def test_draft_tools_are_not_exposed_on_a_connector_scoped_proxy() -> None:
    async with _harness("flat") as harness, harness.connect("author", _PROXY_PATH) as client:
        await harness.set_enabled(True)
        assert not _NAMES.intersection(tool.name for tool in await client.list_tools())
        result = await client.call_tool(_CREATE, {"source": "1"}, raise_on_error=False)
        guidance = _failure(result)
        assert guidance["error"]["code"] == "draft_author_required"
        assert guidance["operation_state"] == "not_started"


async def test_uncertain_draft_write_requires_inspection_and_hides_storage_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    async def write_unconfirmed(_store: DatabaseDraftStore, _author: DraftAuthor, _revision: DraftRevision) -> None:
        raise DraftWriteUnconfirmed(_PRIVATE_SOURCE)

    monkeypatch.setattr(DatabaseDraftStore, "create", write_unconfirmed)
    async with _harness("flat") as harness, harness.connect("author") as client:
        await harness.set_enabled(True)
        result = await client.call_tool(_CREATE, {"source": _PRIVATE_SOURCE}, raise_on_error=False)
        guidance = _failure(result)
        assert guidance["operation_state"] == "unknown"
        assert guidance["recovery"]["retry"] == "inspect_before_retry"
        assert "Do not retry blindly" in repr(result.content)
        assert _PRIVATE_SOURCE not in repr(result)


async def test_validator_startup_failure_reports_that_validation_did_not_start(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    def validation_unavailable(*, max_processes: int, deadline_seconds: float) -> None:
        raise OSError(_PRIVATE_SOURCE)

    monkeypatch.setattr("umbod.mcp.portable_drafts.open_portable_draft_validator", validation_unavailable)
    async with _harness("flat") as harness, harness.connect("author") as client:
        await harness.set_enabled(True)
        receipt = _payload(await client.call_tool(_CREATE, {"source": "1"}))
        result = await client.call_tool(_VALIDATE, {"draft_id": receipt["draft_id"], "revision_id": receipt["revision_id"]}, raise_on_error=False)
        guidance = _failure(result)
        assert guidance["error"]["code"] == "draft_validation_unavailable"
        assert guidance["operation_state"] == "not_started"
        assert "Portable connector draft validation could not initialize" in caplog.text
        assert _PRIVATE_SOURCE not in caplog.text


async def test_validator_outage_is_a_tool_error_not_a_source_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    async def validate_unavailable(_validator: PortableDraftValidation, _revision: DraftRevision) -> DraftValidationReport:
        raise DraftValidationUnavailable(_PRIVATE_SOURCE)

    monkeypatch.setattr(PortableDraftValidation, "validate_saved_revision", validate_unavailable)
    async with _harness("flat") as harness, harness.connect("author") as client:
        await harness.set_enabled(True)
        receipt = _payload(await client.call_tool(_CREATE, {"source": _PRIVATE_SOURCE}))
        result = await client.call_tool(_VALIDATE, {"draft_id": receipt["draft_id"], "revision_id": receipt["revision_id"]}, raise_on_error=False)
        assert _failure(result)["error"]["code"] == "draft_validation_unavailable"
        assert _PRIVATE_SOURCE not in repr(result)


async def test_admin_can_submit_only_owned_exact_revision_while_enabled() -> None:
    source = f"{_SUBMISSION_FIXTURE.read_text(encoding='utf-8')}\n# {_PRIVATE_SOURCE}"
    async with (
        _harness("flat") as harness, harness.connect("admin") as admin,
        harness.connect("author") as member, harness.connect("other_admin") as stranger,
    ):
        session_id = admin.transport.get_session_id()
        assert not connector_tool_name_available("portable_connector", "submit_revision")
        assert not connector_tool_name_available("another_connector", _SUBMIT)
        assert _SUBMIT not in {tool.name for tool in await admin.list_tools()}
        nonexistent = {"draft_id": str(uuid4()), "revision_id": str(uuid4())}
        assert _failure(await admin.call_tool(_SUBMIT, nonexistent, raise_on_error=False))["error"]["code"] == "portable_drafts_disabled"

        await harness.set_enabled(True)
        tools = {tool.name: tool for tool in await admin.list_tools()}
        schema = tools[_SUBMIT].input_schema
        assert set(schema["required"]) == schema["properties"].keys() == {"draft_id", "revision_id"}
        assert schema["additionalProperties"] is False
        assert {item["format"] for item in schema["properties"].values()} == {"uuid"}
        member_tools = {tool.name for tool in await member.list_tools()}
        assert _NAMES <= member_tools and _SUBMIT not in member_tools

        saved = _payload(await admin.call_tool(_CREATE, {"source": source}))
        revision = {"draft_id": saved["draft_id"], "revision_id": saved["revision_id"]}
        assert _payload(await admin.call_tool(_VALIDATE, revision))["status"] == "valid"
        assert await harness.managed_records() == []
        head = _payload(await admin.call_tool(_SAVE, {
            "draft_id": saved["draft_id"], "expected_revision_id": saved["revision_id"],
            "source": source.replace("Workspace", "Changed workspace"),
        }))
        assert _failure(await member.call_tool(_SUBMIT, revision, raise_on_error=False))["error"]["code"] == "portable_submission_administrator_required"
        denied = _failure(await stranger.call_tool(_SUBMIT, revision, raise_on_error=False))
        missing = _failure(await stranger.call_tool(_SUBMIT, nonexistent, raise_on_error=False))
        assert denied == missing
        assert denied["error"]["code"] == "draft_revision_not_found"
        assert await harness.managed_records() == []
        bad_input = await admin.call_tool(_SUBMIT, {**revision, "report": _PRIVATE_SOURCE}, raise_on_error=False)
        assert _failure(bad_input)["error"]["code"] == "invalid_arguments"
        assert _PRIVATE_SOURCE not in repr(bad_input)

        submitted = _payload(await admin.call_tool(_SUBMIT, revision))
        assert submitted == {"connector_id": submitted["connector_id"], "revision_id": saved["revision_id"], "status": "inactive"}
        assert UUID(submitted["connector_id"]).version == 4
        assert submitted["connector_id"] not in revision.values()
        assert _payload(await admin.call_tool(_SUBMIT, revision)) == submitted
        records = await harness.managed_records()
        assert len(records) == 1
        row = records[0]
        assert row.display_name == "Configuration probe"
        assert row.revision_id == saved["revision_id"]
        assert row.source_sha256 == saved["source_sha256"]
        assert loads(row.configuration_schema_json)["properties"]["workspace"]["title"] == "Workspace"
        assert not {"source", "subject", "issuer", "manifest"}.intersection(row.model_dump())
        conflict = await admin.call_tool(_SUBMIT, {**revision, "revision_id": head["revision_id"]}, raise_on_error=False)
        assert _failure(conflict)["error"]["code"] == "portable_submission_conflict"
        assert "configuration_probe" not in {tool.name for tool in await admin.list_tools()}

        await harness.set_enabled(False)
        assert _SUBMIT not in {tool.name for tool in await admin.list_tools()}
        assert _failure(await admin.call_tool(_SUBMIT, revision, raise_on_error=False))["error"]["code"] == "portable_drafts_disabled"
        assert await harness.managed_records() == records
        assert admin.transport.get_session_id() == session_id
        await harness.set_enabled(True)
        assert _payload(await admin.call_tool(_SUBMIT, revision)) == submitted

        private_logs = [
            record for record in harness.logs.invocation_records() if record.attributes.get("mcp.tool.name") == _SUBMIT
        ]
        assert private_logs
        for forbidden in (*revision.values(), _ISSUER, _AUTHOR, _CLIENT_ID, session_id, _PRIVATE_SOURCE):
            assert forbidden not in repr(private_logs)


@pytest.mark.parametrize(
    ("old", "new", "expected_code"),
    [
        ('"workspace"', '"secret_token"', "portable_submission_unsupported_configuration"),
        ('"workspace"', '"constructor"', "portable_submission_unsupported_configuration"),
        ('"workspace"', '"requestSubmit"', "portable_submission_unsupported_configuration"),
        ('"workspace"', '"checkValidity"', "portable_submission_unsupported_configuration"),
        ('"workspace"', '"reportValidity"', "portable_submission_unsupported_configuration"),
        ('"type": "string", "title": "Workspace"', '"type": "object", "title": "Workspace"', "portable_submission_unsupported_configuration"),
        ('"minLength": 1', '"minLength": 10000', "portable_submission_unsupported_configuration"),
        ('"title": "Workspace"', '"title": "Database password"', "portable_submission_unsupported_configuration"),
        ('"title": "Workspace"', '"$ref": "#"', "portable_submission_unsupported_configuration"),
        ('"title": "Workspace"', '"default": "private-source-marker"', "portable_submission_unsupported_configuration"),
        ('"additionalProperties": False', '"additionalProperties": True', "portable_submission_unsupported_configuration"),
        ('    configuration={', '    http_targets={"api": "https://example.invalid"},\n    configuration={', "portable_submission_unsupported_manifest"),
        ('from umbod_sdk.connectors import Connector', 'def broken(:', "portable_submission_invalid_revision"),
    ],
)
async def test_submit_refuses_ineligible_revision_without_writing(old: str, new: str, expected_code: str) -> None:
    source = _SUBMISSION_FIXTURE.read_text(encoding="utf-8").replace(old, new)
    async with _harness("flat") as harness, harness.connect("admin") as client:
        await harness.set_enabled(True)
        stored = _payload(await client.call_tool(_CREATE, {"source": source}))
        result = await client.call_tool(_SUBMIT, {
            "draft_id": stored["draft_id"], "revision_id": stored["revision_id"],
        }, raise_on_error=False)
        guidance = _failure(result)
        assert guidance["error"]["code"] == expected_code
        assert guidance["operation_state"] == "not_started"
        assert _PRIVATE_SOURCE not in repr(result)
        assert await harness.managed_records() == []


async def test_unreadable_settings_hide_and_deny_cached_submit(monkeypatch: pytest.MonkeyPatch) -> None:
    async with _harness("flat") as harness, harness.connect("admin") as client:
        await harness.set_enabled(True)
        assert _SUBMIT in {tool.name for tool in await client.list_tools()}
        stored = _payload(await client.call_tool(_CREATE, {"source": _SUBMISSION_FIXTURE.read_text(encoding="utf-8")}))

        async def unavailable(_service: SystemSettingsService) -> bool:
            raise RuntimeError(_PRIVATE_SOURCE)

        monkeypatch.setattr(SystemSettingsService, "allows_portable_connector_drafts", unavailable)
        assert _SUBMIT not in {tool.name for tool in await client.list_tools()}
        result = await client.call_tool(_SUBMIT, {
            "draft_id": stored["draft_id"], "revision_id": stored["revision_id"],
        }, raise_on_error=False)
        assert _failure(result)["error"]["code"] == "portable_drafts_disabled"
        assert _PRIVATE_SOURCE not in repr(result)
        assert await harness.managed_records() == []


async def test_overlapping_submissions_of_same_revision_share_one_receipt(monkeypatch: pytest.MonkeyPatch) -> None:
    validating = Event()
    release_validation = Event()
    second_read = Event()
    read_count = 0
    validation_count = 0
    validate = PortableDraftValidation.validate_saved_revision
    read = DatabaseDraftStore.read

    async def pause_validation(validator: PortableDraftValidation, revision: DraftRevision) -> DraftValidationReport:
        nonlocal validation_count
        validation_count += 1
        validating.set()
        await release_validation.wait()
        return await validate(validator, revision)

    async def track_read(store: DatabaseDraftStore, author: DraftAuthor, draft_id: UUID, revision_id: UUID) -> DraftRevision:
        nonlocal read_count
        revision = await read(store, author, draft_id, revision_id)
        read_count += 1
        if read_count == 2:
            second_read.set()
        return revision

    monkeypatch.setattr(PortableDraftValidation, "validate_saved_revision", pause_validation)
    monkeypatch.setattr(DatabaseDraftStore, "read", track_read)
    async with _harness("flat") as harness, harness.connect("admin") as first, harness.connect("admin") as second:
        await harness.set_enabled(True)
        stored = _payload(await first.call_tool(_CREATE, {"source": _SUBMISSION_FIXTURE.read_text(encoding="utf-8")}))
        revision = {key: stored[key] for key in ("draft_id", "revision_id")}
        async with TaskGroup() as calls:
            first_call = calls.create_task(first.call_tool(_SUBMIT, revision, raise_on_error=False))
            try:
                await wait_for(validating.wait(), timeout=5)
                second_call = calls.create_task(second.call_tool(_SUBMIT, revision, raise_on_error=False))
                await wait_for(second_read.wait(), timeout=5)
                completed, _ = await wait({second_call}, timeout=0.2)
                assert not completed
            finally:
                release_validation.set()
        assert _payload(first_call.result()) == _payload(second_call.result())
        assert validation_count == 1
        assert len(await harness.managed_records()) == 1


async def test_submit_uncertain_write_reports_safe_inspection_guidance(monkeypatch: pytest.MonkeyPatch) -> None:
    async def unconfirmed(_store: DatabaseManagedConnectorStore, _submission: PortableConnectorSubmission) -> ManagedConnectorReceipt:
        raise ManagedSubmissionWriteUnconfirmed(_PRIVATE_SOURCE)

    monkeypatch.setattr(DatabaseManagedConnectorStore, "submit", unconfirmed)
    source = _SUBMISSION_FIXTURE.read_text(encoding="utf-8")
    async with _harness("flat") as harness, harness.connect("admin") as client:
        await harness.set_enabled(True)
        stored = _payload(await client.call_tool(_CREATE, {"source": source}))
        result = await client.call_tool(_SUBMIT, {
            "draft_id": stored["draft_id"], "revision_id": stored["revision_id"],
        }, raise_on_error=False)
        guidance = _failure(result)
        assert guidance["error"]["code"] == "portable_submission_write_unconfirmed"
        assert guidance["operation_state"] == "unknown"
        assert guidance["recovery"]["retry"] == "inspect_before_retry"
        assert _PRIVATE_SOURCE not in repr(result)
