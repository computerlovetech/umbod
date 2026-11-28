import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, Protocol

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.server.middleware.authorization import _requested_version
from fastmcp.tools import Tool, ToolResult
from mcp.types import CallToolRequestParams, ListToolsRequest
from pydantic import BaseModel, PrivateAttr

from umbod.core.callers import AuthenticationProvenance, CallerContext, DeclaredIssuer, SubjectIdentity, UnavailableIssuer
from umbod.core.connectors.portable.draft_validation import DraftValidationUnavailable, PortableDraftValidation
from umbod.core.connectors.portable.drafts import (
    DatabaseDraftStore, DraftAuthorRequired, DraftHeadChanged, DraftReadUnavailable, DraftRevisionNotFound,
    DraftWriteUnconfirmed, InvalidDraftSource, PortableConnectorDrafts, require_draft_author,
)
from umbod.core.connectors.portable.managed import (
    DatabaseManagedConnectorStore, ManagedSubmissionConflict, ManagedSubmissionInvalidRevision,
    ManagedSubmissionLookupUnavailable, ManagedSubmissionWriteUnconfirmed, PortableConnectorSubmit,
    UnsupportedManagedConfiguration, UnsupportedManagedManifest,
)
from umbod.core.persistence import Database
from umbod.core.responses import RetryAdvice, ToolErrorDetails
from umbod.infrastructure import open_portable_draft_validator
from umbod.mcp.auth.agent_tokens import effective_oauth_provider
from umbod.mcp.auth.caller import authentication_provenance_for_token, caller_context_from_access_token
from umbod.mcp.auth.membership import verified_mcp_caller
from umbod.mcp.connectors.downstream_mcp.provider import _REQUEST_CONNECTOR_SCOPE
from umbod.mcp.responses.progress import operation_completed, operation_rejected_before_work, operation_started
from umbod.mcp.tools.errors import BuiltinToolAuthorizationDenied, BuiltinToolRejected
from umbod.mcp.tools.registration import McpObservedToolRegistrar, tool_result_is_error

from .portable_draft_contracts import (
    RECEIPT_OUTPUT, REPORT_OUTPUT, SOURCE_GUIDANCE, SUBMIT_OUTPUT, CreateDraftInput, SaveRevisionInput,
    SubmitRevisionInput, ValidateRevisionInput, receipt_result, report_result, submit_result,
)
from .portable_draft_names import CREATE_DRAFT, PORTABLE_DRAFT_TOOL_NAMES, SAVE_REVISION, SUBMIT_REVISION, VALIDATE_REVISION

_VALIDATION_CONCURRENCY = 1
_VALIDATION_DEADLINE_SECONDS = 8.0
_AUTHOR_GUIDANCE = "Use the authenticated /mcp endpoint with a verified issuer and subject."
_LOGGER = logging.getLogger(__name__)


def _verified_draft_caller(caller: CallerContext, provider: object) -> CallerContext:
    subject = caller.subject
    if (
        caller.authentication is AuthenticationProvenance.UPSTREAM_VERIFIED
        and type(provider) is GoogleProvider
        and isinstance(subject, SubjectIdentity)
        and isinstance(subject.issuer, UnavailableIssuer)
    ):
        return CallerContext(
            authentication=caller.authentication,
            subject=SubjectIdentity(issuer=DeclaredIssuer(value="https://accounts.google.com"), subject=subject.subject),
        )
    return caller


class PortableDraftSettings(Protocol):
    async def allows_portable_connector_drafts(self) -> bool: ...


class PortableDraftAccess:
    def __init__(self, server: FastMCP, settings: Callable[[], PortableDraftSettings]) -> None:
        self._server = server
        self._settings = settings

    def _author(self) -> CallerContext:
        token = get_access_token()
        if self._server.auth is None or token is None or _REQUEST_CONNECTOR_SCOPE.get():
            raise DraftAuthorRequired()
        provenance = authentication_provenance_for_token(self._server.auth, token)
        if provenance == AuthenticationProvenance.UPSTREAM_VERIFIED:
            verified = verified_mcp_caller(self._server, token)
            if verified is None:
                raise DraftAuthorRequired()
            caller = _verified_draft_caller(verified.caller, effective_oauth_provider(self._server.auth, token))
        else:
            caller = caller_context_from_access_token(token, provenance)
        require_draft_author(caller)
        return caller

    async def _enabled(self) -> bool:
        try:
            return await self._settings().allows_portable_connector_drafts()
        except Exception:
            return False

    async def discoverable(self) -> bool:
        try:
            self._author()
        except DraftAuthorRequired:
            return False
        return await self._enabled()

    async def require(self) -> CallerContext:
        caller = self._author()
        if not await self._enabled():
            raise _rejected("portable_drafts_disabled", "Portable connector drafts are unavailable. Rediscover tools once an administrator has enabled them.", RetryAdvice.NEVER)
        return caller


class PortableSubmissionAccess(PortableDraftAccess):
    def __init__(
        self, server: FastMCP, settings: Callable[[], PortableDraftSettings], administrator_authorized: Callable[[], bool],
    ) -> None:
        super().__init__(server, settings)
        self.administrator_authorized = administrator_authorized

    async def require(self) -> CallerContext:
        caller = await super().require()
        if not self.administrator_authorized():
            message = "Only an authenticated administrator can submit a portable connector revision they own."
            raise BuiltinToolAuthorizationDenied(
                message, details=ToolErrorDetails(code="portable_submission_administrator_required", message=message, issues=()),
            )
        return caller


class PortableDraftVisibility(Middleware):
    def __init__(
        self, access: PortableDraftAccess, submission: PortableSubmissionAccess, registered_tools: Sequence[Tool],
    ) -> None:
        self._access = access
        self._submission = submission
        self._tools = {tool.name: tool for tool in registered_tools}

    async def on_list_tools(
        self, context: MiddlewareContext[ListToolsRequest], call_next: CallNext[ListToolsRequest, Sequence[Tool]],
    ) -> Sequence[Tool]:
        tools = await call_next(context)
        visible = await self._access.discoverable()
        can_submit = visible and self._submission.administrator_authorized()
        return [
            tool for tool in tools
            if tool.name not in PORTABLE_DRAFT_TOOL_NAMES or (
                visible and self._tools.get(tool.name) is tool and (tool.name != SUBMIT_REVISION or can_submit)
            )
        ]

    async def on_call_tool(
        self, context: MiddlewareContext[CallToolRequestParams], call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        name = context.message.name
        if name in PORTABLE_DRAFT_TOOL_NAMES:
            runtime = context.fastmcp_context
            if _REQUEST_CONNECTOR_SCOPE.get():
                return await self._tools[name].run({})
            if runtime is None:
                raise ToolError("Portable connector draft tools are unavailable on this endpoint.")
            resolved = await runtime.fastmcp.get_tool(name, version=_requested_version(context.message.meta))
            if resolved is not self._tools[name]:
                raise ToolError("Portable connector draft tool is unavailable.")
        return await call_next(context)


class PortableDraftValidationRuntime:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._validation: PortableDraftValidation | None = None

    @asynccontextmanager
    async def lifespan(self, authenticated_transport: bool) -> AsyncIterator[None]:
        if not authenticated_transport:
            yield
            return
        async with AsyncExitStack() as stack:
            try:
                validator = await stack.enter_async_context(open_portable_draft_validator(
                    max_processes=_VALIDATION_CONCURRENCY, deadline_seconds=_VALIDATION_DEADLINE_SECONDS,
                ))
                self._validation = PortableDraftValidation(
                    PortableConnectorDrafts(DatabaseDraftStore(self._database)),
                    validator,
                    max_concurrent_validations=_VALIDATION_CONCURRENCY,
                )
            except Exception:
                await stack.aclose()
                _LOGGER.error("Portable connector draft validation could not initialize")
            try:
                yield
            finally:
                self._validation = None

    def current(self) -> PortableDraftValidation:
        if self._validation is None:
            raise DraftValidationUnavailable("Could not start draft validation")
        return self._validation


def _rejected(code: str, message: str, retry: RetryAdvice) -> BuiltinToolRejected:
    return BuiltinToolRejected(message, details=ToolErrorDetails(code=code, message=message, issues=()), retry=retry)


class PortableDraftTool[Command: BaseModel](Tool):
    _access: PortableDraftAccess = PrivateAttr()
    _command: type[Command] = PrivateAttr()
    _execute: Callable[[CallerContext, Command], Awaitable[ToolResult]] = PrivateAttr()

    def __init__(
        self, name: str, description: str, command: type[Command], output_schema: dict[str, Any],
        access: PortableDraftAccess, execute: Callable[[CallerContext, Command], Awaitable[ToolResult]],
    ) -> None:
        super().__init__(name=name, description=description, parameters=command.model_json_schema(), output_schema=output_schema)
        self._access = access
        self._command = command
        self._execute = execute

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            caller = await self._access.require()
            command = self._command.model_validate(arguments)
            return await self._execute(caller, command)
        except DraftAuthorRequired:
            operation_rejected_before_work()
            raise BuiltinToolAuthorizationDenied(_AUTHOR_GUIDANCE, details=ToolErrorDetails(
                code="draft_author_required", message=_AUTHOR_GUIDANCE, issues=(),
            )) from None
        except InvalidDraftSource:
            operation_rejected_before_work()
            raise _rejected("invalid_draft_source", SOURCE_GUIDANCE, RetryAdvice.AFTER_CORRECTION) from None
        except DraftRevisionNotFound:
            operation_rejected_before_work()
            raise _rejected("draft_revision_not_found", "Draft or revision not found. Use identifiers returned by a successful save under this identity.", RetryAdvice.AFTER_CORRECTION) from None
        except DraftHeadChanged:
            operation_rejected_before_work()
            raise _rejected("draft_head_changed", "The expected revision is no longer current. Reconcile the intended changes with the current head before saving; do not blindly retry.", RetryAdvice.AFTER_CORRECTION) from None
        except DraftWriteUnconfirmed:
            raise _rejected("draft_write_unconfirmed", "The write may have committed. Do not retry blindly. If you cannot verify the outcome, stop and contact an administrator with the request ID.", RetryAdvice.INSPECT_BEFORE_RETRY) from None
        except (DraftReadUnavailable, DraftValidationUnavailable):
            raise _rejected("draft_validation_unavailable", "Offline validation is unavailable. No draft was changed. Check service availability before validating this revision again.", RetryAdvice.INSPECT_BEFORE_RETRY) from None


def register_portable_drafts(
    server: FastMCP, registrar: McpObservedToolRegistrar, database: Database,
    settings: Callable[[], PortableDraftSettings], validation: PortableDraftValidationRuntime,
    administrator_authorized: Callable[[], bool],
) -> None:
    access = PortableDraftAccess(server, settings)
    submission_access = PortableSubmissionAccess(server, settings, administrator_authorized)
    submission = PortableConnectorSubmit(
        PortableConnectorDrafts(DatabaseDraftStore(database)), validation.current, DatabaseManagedConnectorStore(database),
    )

    async def create(caller: CallerContext, command: CreateDraftInput) -> ToolResult:
        operation_started()
        receipt = await PortableConnectorDrafts(DatabaseDraftStore(database)).create(caller, command.source)
        operation_completed()
        return receipt_result(receipt)

    async def save(caller: CallerContext, command: SaveRevisionInput) -> ToolResult:
        operation_started()
        receipt = await PortableConnectorDrafts(DatabaseDraftStore(database)).save_revision(
            caller, command.draft_id, command.expected_revision_id, command.source,
        )
        operation_completed()
        return receipt_result(receipt)

    async def validate(caller: CallerContext, command: ValidateRevisionInput) -> ToolResult:
        validator = validation.current()
        operation_started()
        report = await validator.validate_revision(caller, command.draft_id, command.revision_id)
        operation_completed()
        return report_result(report)

    async def submit(caller: CallerContext, command: SubmitRevisionInput) -> ToolResult:
        operation_started()
        try:
            receipt = await submission.submit(caller, command.draft_id, command.revision_id)
        except (DraftReadUnavailable, DraftValidationUnavailable, ManagedSubmissionLookupUnavailable):
            operation_rejected_before_work()
            raise _rejected("portable_submission_unavailable", "Submission could not confirm the revision or its offline validation. Check service availability or validate the revision before retrying.", RetryAdvice.INSPECT_BEFORE_RETRY) from None
        except ManagedSubmissionInvalidRevision:
            operation_rejected_before_work()
            raise _rejected("portable_submission_invalid_revision", "The saved revision did not pass offline validation. Validate it for correction guidance before saving and submitting a new revision.", RetryAdvice.AFTER_CORRECTION) from None
        except UnsupportedManagedManifest:
            operation_rejected_before_work()
            raise _rejected("portable_submission_unsupported_manifest", "Submit a version 1 portable manifest with bounded display metadata and no HTTP targets.", RetryAdvice.AFTER_CORRECTION) from None
        except UnsupportedManagedConfiguration:
            operation_rejected_before_work()
            raise _rejected("portable_submission_unsupported_configuration", "Use a flat, closed configuration object with bounded noncredential string fields. Only titles, length bounds, and string enums are supported on fields.", RetryAdvice.AFTER_CORRECTION) from None
        except ManagedSubmissionConflict:
            operation_rejected_before_work()
            raise _rejected("portable_submission_conflict", "This draft already has a different submitted revision. Only the original submitted revision can be resubmitted.", RetryAdvice.AFTER_CORRECTION) from None
        except ManagedSubmissionWriteUnconfirmed:
            raise _rejected("portable_submission_write_unconfirmed", "The submission may have committed. Do not retry blindly. If you cannot verify the outcome, contact an administrator with the request ID.", RetryAdvice.INSPECT_BEFORE_RETRY) from None
        operation_completed()
        return submit_result(receipt)

    tools = (
        PortableDraftTool(CREATE_DRAFT, f"Create a private portable connector draft and save its first immutable revision. Saving does not run code, even if syntax is invalid, or publish a tool. {SOURCE_GUIDANCE} Keep the returned draft and revision UUIDs.", CreateDraftInput, RECEIPT_OUTPUT.json_schema(), access, create),
        PortableDraftTool(SAVE_REVISION, f"Save a complete replacement as a new immutable revision without running or publishing it. Use the draft UUID and its current head as expected_revision_id; stale heads are rejected. {SOURCE_GUIDANCE}", SaveRevisionInput, RECEIPT_OUTPUT.json_schema(), access, save),
        PortableDraftTool(VALIDATE_REVISION, "Check the exact saved revision UUID for this draft, even if the head has moved. Returns valid, invalid, or inconclusive for the reported profile. Handler imports are advisory; no handler, configuration check, network request, or publication occurs.", ValidateRevisionInput, REPORT_OUTPUT.json_schema(), access, validate),
        PortableDraftTool(SUBMIT_REVISION, "As an administrator who owns the draft, submit an exact saved revision UUID for offline validation and creation of an inactive managed connector. Repeating the same submission returns its existing ID; submitting a different revision of that draft conflicts. Submission does not execute handlers, activate, or publish anything.", SubmitRevisionInput, SUBMIT_OUTPUT.json_schema(), submission_access, submit),
    )
    registered = [registrar.register_tool(tool, result_is_error=tool_result_is_error, operation_names=frozenset(), builtin_response=True) for tool in tools]
    server.add_middleware(PortableDraftVisibility(access, submission_access, registered))
