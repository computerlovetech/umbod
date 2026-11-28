from typing import Annotated, Literal, NotRequired, TypedDict
from uuid import UUID

from fastmcp.tools import ToolResult
from mcp.types import TextContent
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from umbod.core.connectors.portable.draft_validation import DraftDiagnostic, DraftValidationReport, ValidationChecks
from umbod.core.connectors.portable.draft_validation.models import DiagnosticStage, ValidationStatus
from umbod.core.connectors.portable.drafts import MAX_DRAFT_SOURCE_BYTES, DraftReceipt
from umbod.core.connectors.portable.managed import ManagedConnectorReceipt

SOURCE_GUIDANCE = "Provide complete, nonblank Python source as text (maximum 64 KiB in UTF-8). Do not include secrets."


class CreateDraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Annotated[str, Field(min_length=1, max_length=MAX_DRAFT_SOURCE_BYTES, description=SOURCE_GUIDANCE)]


class SaveRevisionInput(CreateDraftInput):
    draft_id: Annotated[UUID, Field(description="Draft UUID returned by portable_connector_create_draft.")]
    expected_revision_id: Annotated[UUID, Field(description="Current head revision UUID from the most recent successful write; stale revisions cannot be overwritten.")]


class ValidateRevisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: Annotated[UUID, Field(description="Draft UUID returned by portable_connector_create_draft.")]
    revision_id: Annotated[UUID, Field(description="Exact saved revision UUID to check, even if the head has moved.")]


class SubmitRevisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: Annotated[UUID, Field(description="Private draft UUID you own, returned by portable_connector_create_draft.")]
    revision_id: Annotated[UUID, Field(description="Exact saved revision UUID to submit, even if the head has moved.")]


class ValidationDiagnosticOutput(TypedDict):
    code: str
    stage: DiagnosticStage
    severity: Literal["error", "warning"]
    message: str
    action: NotRequired[str]
    line: NotRequired[Annotated[int, Field(ge=1)]]
    column: NotRequired[Annotated[int, Field(ge=1)]]


class ValidationReportOutput(TypedDict):
    draft_id: UUID
    revision_id: UUID
    profile_id: str
    status: ValidationStatus
    checks: ValidationChecks
    diagnostics: Annotated[list[ValidationDiagnosticOutput], Field(max_length=20)]
    diagnostics_truncated: bool


RECEIPT_OUTPUT = TypeAdapter(DraftReceipt)
REPORT_OUTPUT = TypeAdapter(ValidationReportOutput)
SUBMIT_OUTPUT = TypeAdapter(ManagedConnectorReceipt)


def submit_result(receipt: ManagedConnectorReceipt) -> ToolResult:
    return ToolResult(structured_content=SUBMIT_OUTPUT.dump_python(receipt, mode="json"))


def receipt_result(receipt: DraftReceipt) -> ToolResult:
    return ToolResult(structured_content=RECEIPT_OUTPUT.dump_python(receipt, mode="json"))


def _diagnostic_output(diagnostic: DraftDiagnostic) -> ValidationDiagnosticOutput:
    result = ValidationDiagnosticOutput(
        code=diagnostic.code, stage=diagnostic.stage, severity=diagnostic.severity, message=diagnostic.message,
    )
    if diagnostic.action:
        result["action"] = diagnostic.action
    if diagnostic.positions:
        position = diagnostic.positions[0]
        result.update(line=position.line, column=position.column)
    return result


def report_result(report: DraftValidationReport) -> ToolResult:
    outcome = report.outcome
    diagnostics = [_diagnostic_output(diagnostic) for diagnostic in outcome.diagnostics]
    payload = ValidationReportOutput(
        draft_id=report.draft_id, revision_id=report.revision_id, profile_id=report.profile_id,
        status=outcome.status, checks=outcome.checks, diagnostics=diagnostics,
        diagnostics_truncated=outcome.diagnostics_truncated,
    )
    text = [f"Offline validation: {outcome.status} for this saved revision and profile. Handler imports are advisory. Umbod did not invoke any handler or configuration check, and nothing was published."]
    text.extend(f"{item['message']} {item.get('action', '')}".rstrip() for item in diagnostics)
    if outcome.diagnostics_truncated:
        text.append("Additional diagnostics were omitted.")
    return ToolResult(
        content=[TextContent(type="text", text="\n".join(text))],
        structured_content=REPORT_OUTPUT.dump_python(payload, mode="json"),
    )
