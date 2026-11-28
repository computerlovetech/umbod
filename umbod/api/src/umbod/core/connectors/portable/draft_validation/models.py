from dataclasses import dataclass
from typing import Literal
from uuid import UUID


type ValidationStatus = Literal["valid", "invalid", "inconclusive"]
type CheckStatus = Literal["passed", "failed", "not_checked", "warnings"]
type DiagnosticStage = Literal["load", "manifest", "handler_imports"]


@dataclass(frozen=True, slots=True)
class SourcePosition:
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class DraftDiagnostic:
    code: str
    stage: DiagnosticStage
    severity: Literal["error", "warning"]
    message: str
    action: str
    positions: tuple[SourcePosition, ...]


@dataclass(frozen=True, slots=True)
class ValidationChecks:
    load: CheckStatus
    manifest: CheckStatus
    handler_imports: CheckStatus
    handler_execution: Literal["not_checked"]


@dataclass(frozen=True, slots=True)
class ValidationOutcome:
    status: ValidationStatus
    checks: ValidationChecks
    diagnostics: tuple[DraftDiagnostic, ...]
    diagnostics_truncated: bool


@dataclass(frozen=True, slots=True)
class DraftValidationReport:
    draft_id: UUID
    revision_id: UUID
    profile_id: str
    outcome: ValidationOutcome
