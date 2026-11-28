from asyncio import Event, create_subprocess_exec, create_task, wait_for
from asyncio.subprocess import Process
from collections.abc import AsyncIterator
from pathlib import Path
from sys import executable
from uuid import uuid4

import pytest
import pytest_asyncio
from pydantic_monty import AsyncMonty

from tests.persistence_runtime import prepared_inmemory_runtime
from umbod.core.callers import AuthenticationProvenance, CallerContext, DeclaredIssuer, SubjectIdentity
from umbod.core.connectors.portable.draft_validation import (
    DraftValidationReport,
    DraftValidationUnavailable,
    PortableDraftValidation,
    SourcePosition,
    ValidationChecks,
    ValidationOutcome,
)
from umbod.core.connectors.portable.drafts import DatabaseDraftStore, DraftRevisionNotFound, PortableConnectorDrafts
from umbod.infrastructure.portable_connectors import MontyDraftSourceValidator, portable_sdk_mount
from umbod.infrastructure.portable_connectors import draft_validator

pytestmark = pytest.mark.asyncio

_FIXTURES = Path(__file__).with_name("fixtures")
_AUTHOR = CallerContext(
    authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
    subject=SubjectIdentity(issuer=DeclaredIssuer(value="https://accounts.example"), subject="author"),
)
_OTHER_AUTHOR = _AUTHOR.model_copy(update={
    "subject": SubjectIdentity(issuer=DeclaredIssuer(value="https://accounts.example"), subject="other"),
})


class _GatedValidator:
    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()
        self.sources: list[str] = []

    @property
    def profile_id(self) -> str:
        return "test-profile"

    async def validate(self, source: str) -> ValidationOutcome:
        self.sources.append(source)
        self.entered.set()
        await self.release.wait()
        return ValidationOutcome(
            "valid", ValidationChecks("passed", "passed", "passed", "not_checked"), (), False,
        )


@pytest_asyncio.fixture
async def author_drafts() -> AsyncIterator[PortableConnectorDrafts]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield PortableConnectorDrafts(DatabaseDraftStore(runtime.database))
    finally:
        await runtime.shutdown()


@pytest_asyncio.fixture
async def validator() -> AsyncIterator[MontyDraftSourceValidator]:
    with portable_sdk_mount() as mount:
        async with AsyncMonty(max_processes=1) as pool:
            yield MontyDraftSourceValidator(pool, mount, 8)


@pytest.fixture
def validation(author_drafts: PortableConnectorDrafts, validator: MontyDraftSourceValidator) -> PortableDraftValidation:
    return PortableDraftValidation(author_drafts, validator, max_concurrent_validations=1)


@pytest.fixture
def connector_source() -> str:
    return (_FIXTURES / "issue_tracker.py").read_text(encoding="utf-8")


async def _validate(
    author_drafts: PortableConnectorDrafts, validation: PortableDraftValidation, source: str
) -> DraftValidationReport:
    saved = await author_drafts.create(_AUTHOR, source)
    return await validation.validate_revision(_AUTHOR, saved.draft_id, saved.revision_id)


async def test_validation_reports_unavailable_load_import_and_keeps_source(
    author_drafts: PortableConnectorDrafts, validation: PortableDraftValidation, connector_source: str,
) -> None:
    source = "\nimport requests\n" + connector_source
    report = await _validate(author_drafts, validation, source)
    diagnostic, = report.outcome.diagnostics

    assert report.outcome.status == "invalid"
    assert report.outcome.checks == ValidationChecks("failed", "not_checked", "not_checked", "not_checked")
    assert diagnostic.code == "import_unavailable"
    assert "`requests`" in diagnostic.message
    assert "HttpContext" in diagnostic.action
    assert diagnostic.positions == (SourcePosition(2, 1),)
    assert (await author_drafts.read_revision(_AUTHOR, report.draft_id, report.revision_id)).source == source


@pytest.mark.parametrize(
    "source, code", [("def invalid(:\n", "syntax_error"), ("raise ValueError('private source text')", "initialization_error")],
)
async def test_load_diagnostics_do_not_return_raw_errors(
    author_drafts: PortableConnectorDrafts, validation: PortableDraftValidation, source: str, code: str,
) -> None:
    report = await _validate(author_drafts, validation, source)
    diagnostic, = report.outcome.diagnostics

    assert report.outcome.status == "invalid"
    assert diagnostic.code == code
    assert "private source text" not in repr(report)
    assert "def invalid" not in repr(report)


async def test_successful_load_without_connector_fails_manifest(
    author_drafts: PortableConnectorDrafts, validation: PortableDraftValidation
) -> None:
    report = await _validate(author_drafts, validation, "other = 42")

    assert report.outcome.status == "invalid"
    assert report.outcome.checks == ValidationChecks("passed", "failed", "not_checked", "not_checked")
    assert report.outcome.diagnostics[0].code == "invalid_manifest"


async def test_invalid_json_schema_is_rejected_without_raw_payload(
    author_drafts: PortableConnectorDrafts, validation: PortableDraftValidation, connector_source: str,
) -> None:
    source = connector_source.replace('"type": "string"', '"type": "private_invalid_schema_type"')
    report = await _validate(author_drafts, validation, source)

    assert report.outcome.status == "invalid"
    assert report.outcome.diagnostics[0].code == "invalid_manifest"
    assert "private_invalid_schema_type" not in repr(report)


async def test_deferred_import_warning_does_not_claim_a_handler_ran(
    author_drafts: PortableConnectorDrafts, validation: PortableDraftValidation, connector_source: str,
) -> None:
    source = connector_source.replace("    result = await", "    import requests\n    result = await")
    report = await _validate(author_drafts, validation, source)

    assert report.outcome.status == "valid"
    assert report.outcome.checks == ValidationChecks("passed", "passed", "warnings", "not_checked")
    assert len(report.outcome.diagnostics) == 1
    warning = report.outcome.diagnostics[0]
    assert warning.severity == "warning"
    assert "requests" in warning.message
    assert warning.positions


async def test_unavailable_name_from_supported_module_is_an_advisory_warning(
    author_drafts: PortableConnectorDrafts, validation: PortableDraftValidation, connector_source: str,
) -> None:
    source = connector_source.replace("    result = await", "    from json import missing_draft_export\n    result = await")
    report = await _validate(author_drafts, validation, source)

    assert report.outcome.status == "valid"
    assert report.outcome.checks.handler_execution == "not_checked"
    warning, = report.outcome.diagnostics
    assert warning.code == "handler_import_unavailable"
    assert "missing_draft_export" in warning.message


async def test_advisory_diagnostics_are_bounded_and_report_truncation(
    author_drafts: PortableConnectorDrafts, validation: PortableDraftValidation, connector_source: str,
) -> None:
    imports = "".join(f"    import absent_draft_module_{index}\n" for index in range(21))
    source = connector_source + "\ndef deferred_imports():\n" + imports
    report = await _validate(author_drafts, validation, source)

    assert report.outcome.status == "valid"
    assert report.outcome.checks.handler_imports == "warnings"
    assert len(report.outcome.diagnostics) == 20
    assert report.outcome.diagnostics_truncated


async def test_validation_uses_saved_revision_and_never_invokes_handlers(
    author_drafts: PortableConnectorDrafts, validation: PortableDraftValidation, connector_source: str,
) -> None:
    source = connector_source.replace("    result = await", '    import json\n    raise ValueError("not executed")\n    result = await')
    old = await author_drafts.create(_AUTHOR, source)
    await author_drafts.save_revision(_AUTHOR, old.draft_id, old.revision_id, "import requests")

    report = await validation.validate_revision(_AUTHOR, old.draft_id, old.revision_id)

    assert report.revision_id == old.revision_id
    assert report.outcome.status == "valid"
    assert report.outcome.checks == ValidationChecks("passed", "passed", "passed", "not_checked")
    assert not report.outcome.diagnostics
    assert report.profile_id.startswith("portable-monty-")


async def test_catalog_configuration_probe_is_valid_without_running_its_handlers(
    author_drafts: PortableConnectorDrafts, validation: PortableDraftValidation,
) -> None:
    source = (_FIXTURES / "configuration_probe.py").read_text(encoding="utf-8")

    report = await _validate(author_drafts, validation, source)

    assert report.outcome.status == "valid"
    assert report.outcome.checks.handler_execution == "not_checked"
    assert not report.outcome.diagnostics


async def test_validation_has_no_http_binding(
    author_drafts: PortableConnectorDrafts, validation: PortableDraftValidation, connector_source: str,
) -> None:
    report = await _validate(author_drafts, validation, "from umbod_http_binding import dispatch\n" + connector_source)

    assert report.outcome.status == "invalid"
    assert report.outcome.diagnostics[0].code == "import_unavailable"


async def test_validation_has_no_host_data_mount(
    author_drafts: PortableConnectorDrafts, validation: PortableDraftValidation, connector_source: str, tmp_path: Path,
) -> None:
    sentinel = tmp_path / "host-only.txt"
    sentinel.write_text("private contents", encoding="utf-8")
    source = f"from pathlib import Path\nPath({str(sentinel)!r}).read_text()\n" + connector_source
    report = await _validate(author_drafts, validation, source)

    assert report.outcome.status == "invalid"
    assert report.outcome.checks.load == "failed"
    assert "private contents" not in repr(report)
    assert str(sentinel) not in repr(report)


async def test_oversized_manifest_is_inconclusive(
    author_drafts: PortableConnectorDrafts, validation: PortableDraftValidation, connector_source: str,
) -> None:
    source = connector_source.replace('description="Manage issues in the configured project."', 'description="x" * 70000')
    report = await _validate(author_drafts, validation, source)

    assert report.outcome.status == "inconclusive"
    assert report.outcome.checks.manifest == "not_checked"
    assert report.outcome.diagnostics[0].code == "validation_limit"


async def test_runtime_budget_exhaustion_is_inconclusive(
    author_drafts: PortableConnectorDrafts, validation: PortableDraftValidation,
) -> None:
    report = await _validate(author_drafts, validation, "def recurse():\n    return recurse()\nrecurse()\n")

    assert report.outcome.status == "inconclusive"
    assert report.outcome.diagnostics[0].code == "validation_limit"


async def test_manifest_inspection_does_not_call_an_authored_override(
    author_drafts: PortableConnectorDrafts, validation: PortableDraftValidation, connector_source: str,
) -> None:
    source = connector_source + (
        '\ndef authored_manifest():\n    raise RuntimeError("not executed")\nconnector.manifest = authored_manifest\n'
    )
    report = await _validate(author_drafts, validation, source)

    assert report.outcome.status == "valid"
    assert report.outcome.checks.manifest == "passed"


async def test_validation_deadline_kills_manifest_worker(
    author_drafts: PortableConnectorDrafts, connector_source: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    workers: list[Process] = []

    async def start_slow_worker(*_command: str, **options: int) -> Process:
        worker = await create_subprocess_exec(executable, "-c", "from time import sleep; sleep(30)", **options)
        workers.append(worker)
        return worker

    monkeypatch.setattr(draft_validator, "create_subprocess_exec", start_slow_worker)
    with portable_sdk_mount() as mount:
        async with AsyncMonty(max_processes=1) as pool:
            validation = PortableDraftValidation(author_drafts, MontyDraftSourceValidator(pool, mount, 2), 1)
            report = await _validate(author_drafts, validation, connector_source)

    assert report.outcome.status == "inconclusive"
    assert report.outcome.diagnostics[0].stage == "manifest"
    worker, = workers
    assert worker.returncode is not None


async def test_worker_unavailability_is_not_reported_as_invalid_author_source(author_drafts: PortableConnectorDrafts) -> None:
    with portable_sdk_mount() as mount:
        pool = AsyncMonty(max_processes=1)
        async with pool:
            unstarted = MontyDraftSourceValidator(pool, mount, 8)
        validation = PortableDraftValidation(author_drafts, unstarted, 1)
        with pytest.raises(DraftValidationUnavailable, match="validator is unavailable"):
            await _validate(author_drafts, validation, "x = 42")


async def test_foreign_and_missing_revisions_do_not_start_validation(author_drafts: PortableConnectorDrafts) -> None:
    validator = _GatedValidator()
    validation = PortableDraftValidation(author_drafts, validator, 1)
    saved = await author_drafts.create(_AUTHOR, "private source")

    with pytest.raises(DraftRevisionNotFound):
        await validation.validate_revision(_OTHER_AUTHOR, saved.draft_id, saved.revision_id)
    with pytest.raises(DraftRevisionNotFound):
        await validation.validate_revision(_AUTHOR, saved.draft_id, uuid4())
    assert not validator.sources


async def test_validation_rejects_excess_concurrency_without_queueing(author_drafts: PortableConnectorDrafts) -> None:
    validator = _GatedValidator()
    validation = PortableDraftValidation(author_drafts, validator, 1)
    saved = await author_drafts.create(_AUTHOR, "source")
    running = create_task(validation.validate_revision(_AUTHOR, saved.draft_id, saved.revision_id))
    try:
        await wait_for(validator.entered.wait(), timeout=2)
        with pytest.raises(DraftValidationUnavailable, match="validator is busy"):
            await validation.validate_revision(_AUTHOR, saved.draft_id, saved.revision_id)
    finally:
        validator.release.set()
        await running
    assert validator.sources == ["source"]
