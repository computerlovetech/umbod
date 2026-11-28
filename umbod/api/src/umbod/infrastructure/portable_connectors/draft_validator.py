from asyncio import CancelledError, create_subprocess_exec, get_running_loop, timeout_at
from asyncio.subprocess import DEVNULL, PIPE
from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from math import isfinite
from pathlib import Path
from sys import executable

from pydantic_monty import (
    AsyncMonty,
    CollectStreams,
    MontyConversionError,
    MontyCrashedError,
    MontyError,
    MontyRuntimeError,
    MontySyntaxError,
    MountDir,
    __version__,
)

from umbod.core.connectors.portable.draft_validation import (
    DraftDiagnostic,
    DraftValidationUnavailable,
    SourcePosition,
    ValidationChecks,
    ValidationOutcome,
)
from umbod.core.connectors.portable.draft_validation.models import CheckStatus, DiagnosticStage, ValidationStatus
from umbod.core.connectors.portable.drafts import MAX_DRAFT_SOURCE_BYTES
from .draft_imports import inspect_handler_imports, module_on_import_line
from .draft_manifest_worker import INVALID_MANIFEST_EXIT_CODE
from .sandbox import PORTABLE_LIMITS, bootstrap_portable_sdk

_SOURCE_FEED = "<python-input-1>"
_MAX_MANIFEST_NODES = 2048
_MAX_MANIFEST_DEPTH = 20
_MAX_MANIFEST_TEXT = 64 * 1024
_MAX_GUEST_OUTPUT = 16 * 1024
_VALIDATION_RULES_VERSION = 1
_EXPORT_MANIFEST = """from umbod_sdk.connectors import Connector as _UmbodConnector
if type(connector) is not _UmbodConnector:
    raise TypeError("Expected an SDK Connector")
_umbod_draft_snapshot = _UmbodConnector(
    id=connector.id,
    name=connector.name,
    description=connector.description,
    capability_description=connector.capability_description,
    configuration=connector.configuration,
    http_targets=connector._http_targets,
)
_umbod_draft_snapshot._handlers = connector._handlers
_umbod_draft_snapshot._tool_manifests = connector._tool_manifests
_umbod_draft_manifest = _UmbodConnector.manifest(_umbod_draft_snapshot)
_UmbodConnector._handler(_umbod_draft_snapshot, _umbod_draft_manifest["configuration_check_handler_id"])
for _umbod_draft_tool in _umbod_draft_manifest["tools"]:
    _UmbodConnector._handler(_umbod_draft_snapshot, _umbod_draft_tool["handler_id"])
_umbod_draft_manifest
"""


@dataclass(slots=True)
class _ValidationProgress:
    load: CheckStatus
    manifest: CheckStatus
    stage: DiagnosticStage
    analysing_source: bool

    def result(
        self,
        status: ValidationStatus,
        diagnostics: tuple[DraftDiagnostic, ...],
        *,
        handler_imports: CheckStatus,
        truncated: bool,
    ) -> ValidationOutcome:
        return ValidationOutcome(
            status=status,
            checks=ValidationChecks(self.load, self.manifest, handler_imports, "not_checked"),
            diagnostics=diagnostics,
            diagnostics_truncated=truncated,
        )

    def stopped(self, diagnostic: DraftDiagnostic) -> ValidationOutcome:
        return self.result("inconclusive", (diagnostic,), handler_imports="not_checked", truncated=False)

    def invalid(self, diagnostic: DraftDiagnostic) -> ValidationOutcome:
        if diagnostic.stage == "load":
            self.load = "failed"
        if diagnostic.stage == "manifest":
            self.manifest = "failed"
        return self.result("invalid", (diagnostic,), handler_imports="not_checked", truncated=False)


class MontyDraftSourceValidator:
    def __init__(self, pool: AsyncMonty, sdk_mount: MountDir, deadline_seconds: float) -> None:
        if not isfinite(deadline_seconds) or deadline_seconds <= 0:
            raise ValueError("The validation deadline must be positive and finite")
        if sdk_mount.mode != "read-only" or sdk_mount.virtual_path != "/sdk":
            raise ValueError("Draft validation requires the read-only portable SDK mount")
        self._pool = pool
        self._mount = sdk_mount
        self._deadline_seconds = deadline_seconds
        self._profile_id = _profile_id(sdk_mount)

    @property
    def profile_id(self) -> str:
        return self._profile_id

    async def validate(self, source: str) -> ValidationOutcome:
        if len(source) > MAX_DRAFT_SOURCE_BYTES or len(source.encode("utf-8")) > MAX_DRAFT_SOURCE_BYTES:
            raise ValueError("Draft source exceeds the validation input limit")
        progress = _ValidationProgress("not_checked", "not_checked", "load", False)
        clock = get_running_loop().time
        expires_at = clock() + self._deadline_seconds
        deadline = timeout_at(expires_at)
        try:
            async with deadline:
                result = await self._validate(source, progress, expires_at)
                if clock() >= expires_at:
                    return progress.stopped(_budget_diagnostic(progress.stage))
                return result
        except MontyCrashedError as error:
            if error.timed_out and progress.analysing_source:
                return progress.stopped(_budget_diagnostic(progress.stage))
            raise DraftValidationUnavailable("The draft validator is unavailable") from None
        except TimeoutError:
            if deadline.expired() and progress.analysing_source:
                return progress.stopped(_budget_diagnostic(progress.stage))
            raise DraftValidationUnavailable("The draft validator is unavailable") from None
        except (MontyError, OSError, RuntimeError, TypeError, ValueError):
            raise DraftValidationUnavailable("The draft validator is unavailable") from None

    async def _validate(self, source: str, progress: _ValidationProgress, expires_at: float) -> ValidationOutcome:
        async with self._pool.checkout(limits=PORTABLE_LIMITS) as session:
            await bootstrap_portable_sdk(session, self._mount)
            progress.analysing_source = True
            guest_output = CollectStreams(max_bytes=_MAX_GUEST_OUTPUT)
            try:
                await session.feed_run(source, cwd="/", print_callback=guest_output)
            except (MontySyntaxError, MontyRuntimeError) as error:
                return _source_failure(source, error, progress)
            except MontyConversionError:
                return progress.invalid(_load_diagnostic("unsupported_runtime_value", ()))
            progress.load = "passed"
            progress.stage = "manifest"
            try:
                raw_manifest = await session.feed_run(_EXPORT_MANIFEST, cwd="/", print_callback=guest_output)
            except MontyRuntimeError as error:
                if _is_runtime_limit(error):
                    return progress.stopped(_budget_diagnostic("manifest"))
                return progress.invalid(_invalid_manifest())
            except MontyConversionError:
                return progress.invalid(_invalid_manifest())
        if get_running_loop().time() >= expires_at:
            return progress.stopped(_budget_diagnostic("manifest"))
        try:
            if not _within_manifest_budget(raw_manifest):
                return progress.stopped(_budget_diagnostic("manifest"))
            payload = dumps(raw_manifest, allow_nan=False).encode("ascii")
        except (TypeError, ValueError):
            return progress.invalid(_invalid_manifest())
        if not await _validate_manifest_frame(payload):
            return progress.invalid(_invalid_manifest())
        progress.manifest = "passed"
        if get_running_loop().time() >= expires_at:
            return progress.stopped(_budget_diagnostic("manifest"))

        progress.stage = "handler_imports"
        progress.analysing_source = False
        async with self._pool.checkout(limits=PORTABLE_LIMITS) as session:
            await bootstrap_portable_sdk(session, self._mount)
            progress.analysing_source = True
            warnings, truncated = await inspect_handler_imports(session, source)
        return progress.result(
            "valid", warnings, handler_imports="warnings" if warnings or truncated else "passed", truncated=truncated
        )


def _profile_id(mount: MountDir) -> str:
    connectors = Path(mount.host_path) / "umbod_sdk" / "connectors"
    digest = sha256()
    for name in ("__init__.py", "http.py"):
        digest.update(sha256((connectors / name).read_bytes()).digest())
    return f"portable-monty-{__version__}-{digest.hexdigest()}-rules-{_VALIDATION_RULES_VERSION}"


async def _validate_manifest_frame(payload: bytes) -> bool:
    worker = await create_subprocess_exec(
        executable, "-c",
        "from umbod.infrastructure.portable_connectors.draft_manifest_worker import main; raise SystemExit(main())",
        stdin=PIPE, stdout=DEVNULL, stderr=DEVNULL,
    )
    try:
        await worker.communicate(payload)
    except CancelledError:
        try:
            worker.kill()
        except ProcessLookupError:
            pass
        await worker.wait()
        raise
    if worker.returncode == 0:
        return True
    if worker.returncode == INVALID_MANIFEST_EXIT_CODE:
        return False
    raise DraftValidationUnavailable("The draft validator is unavailable")


def _within_manifest_budget(raw: object) -> bool:
    pending = [(raw, 0)]
    remaining_nodes = _MAX_MANIFEST_NODES
    remaining_text = _MAX_MANIFEST_TEXT
    while pending:
        value, depth = pending.pop()
        remaining_nodes -= 1
        if remaining_nodes < 0 or depth > _MAX_MANIFEST_DEPTH:
            return False
        if isinstance(value, str):
            remaining_text -= len(value)
        elif isinstance(value, dict):
            if 2 * len(value) > remaining_nodes - len(pending):
                return False
            for key, child in value.items():
                pending.extend(((key, depth + 1), (child, depth + 1)))
        elif isinstance(value, list):
            if len(value) > remaining_nodes - len(pending):
                return False
            pending.extend((child, depth + 1) for child in value)
        elif value is not None and type(value) not in {bool, int, float}:
            raise ValueError("Expected a JSON value")
        if remaining_text < 0:
            return False
    return True


def _source_failure(
    source: str, error: MontyRuntimeError | MontySyntaxError, progress: _ValidationProgress
) -> ValidationOutcome:
    positions = _source_position(source, error)
    if isinstance(error, MontySyntaxError):
        return progress.invalid(_load_diagnostic("syntax_error", positions))
    problem = error.exception()
    if _is_runtime_limit(error):
        return progress.stopped(_budget_diagnostic("load"))
    if isinstance(problem, ImportError):
        module = module_on_import_line(source, positions[0].line) if positions else ""
        return progress.invalid(_import_diagnostic(module, positions))
    if isinstance(problem, NotImplementedError):
        return progress.invalid(_load_diagnostic("unsupported_runtime_feature", positions))
    return progress.invalid(_load_diagnostic("initialization_error", positions))


def _source_position(source: str, error: MontyRuntimeError | MontySyntaxError) -> tuple[SourcePosition, ...]:
    lines = source.split("\n")
    for frame in reversed(error.traceback()):
        if frame.filename == _SOURCE_FEED and 1 <= frame.line <= len(lines) and frame.column > 0:
            return (SourcePosition(frame.line, frame.column),)
    return ()


def _is_runtime_limit(error: MontyRuntimeError) -> bool:
    return isinstance(error.exception(), (TimeoutError, MemoryError, RecursionError))


def _load_diagnostic(code: str, positions: tuple[SourcePosition, ...]) -> DraftDiagnostic:
    messages = {
        "syntax_error": ("Monty could not parse the connector source", "Correct the syntax near the reported line."),
        "unsupported_runtime_value": ("Monty could not export the initialization result", "Remove the module-level result."),
        "unsupported_runtime_feature": ("The connector used an operation Monty does not support", "Use a supported portable operation."),
        "initialization_error": ("The connector raised an error while loading", "Check the module-level code near the reported line."),
    }
    message, action = messages[code]
    return DraftDiagnostic(code, "load", "error", message, action, positions)


def _import_diagnostic(module: str, positions: tuple[SourcePosition, ...]) -> DraftDiagnostic:
    message = f"Monty could not import `{module}`" if module else "Monty could not complete an import"
    action = "Use the SDK's HttpContext for HTTP." if module in {"requests", "httpx", "httpx2", "aiohttp"} else (
        "Use a module and names available in the selected portable runtime profile."
    )
    return DraftDiagnostic("import_unavailable", "load", "error", message, action, positions)


def _invalid_manifest() -> DraftDiagnostic:
    return DraftDiagnostic(
        "invalid_manifest", "manifest", "error", "The connector did not export a valid portable manifest",
        "Define a module-level SDK connector with an explicit configuration schema, a check, and at least one tool.", (),
    )


def _budget_diagnostic(stage: DiagnosticStage) -> DraftDiagnostic:
    return DraftDiagnostic(
        "validation_limit", stage, "warning", "Validation stopped at a runtime or document limit",
        "Reduce module-level work or simplify the manifest and validate the revision again.", (),
    )
