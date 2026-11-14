from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from umbod.core.callers import CallerContext

Identifier = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{0,63}$")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
AssessmentStatus = Literal["observed", "not_observed", "not_assessed"]


class BehaviourModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BehaviourPattern(BehaviourModel):
    id: Identifier
    name: Name
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    assessment_prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    inclusion_criteria: str = Field(max_length=4000)
    exclusion_criteria: str = Field(max_length=4000)
    categories: tuple[Identifier, ...] = Field(max_length=10)
    polarity: Literal["positive", "negative", "neutral"]
    enabled: bool

    @model_validator(mode="after")
    def unique_categories(self) -> Self:
        if len(set(self.categories)) != len(self.categories):
            raise ValueError("Categories must be unique")
        return self


class DiagnosticPlaybook(BehaviourModel):
    id: Identifier
    name: Name
    collection_instructions: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]
    pattern_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=20)
    enabled: bool
    allow_proactive: bool

    @model_validator(mode="after")
    def unique_patterns(self) -> Self:
        if len(set(self.pattern_ids)) != len(self.pattern_ids):
            raise ValueError("Selected patterns must be unique")
        return self


class BehaviourConfiguration(BehaviourModel):
    revision: int = Field(ge=0)
    patterns: tuple[BehaviourPattern, ...] = Field(max_length=50)
    playbooks: tuple[DiagnosticPlaybook, ...] = Field(max_length=20)


class PublishConfiguration(BehaviourModel):
    expected_revision: int = Field(ge=0)
    patterns: tuple[BehaviourPattern, ...] = Field(max_length=50)
    playbooks: tuple[DiagnosticPlaybook, ...] = Field(max_length=20)


class DiagnosticInstructions(BehaviourModel):
    configuration_revision: int = Field(ge=1)
    playbook: DiagnosticPlaybook
    patterns: tuple[BehaviourPattern, ...]
    reporting_guidance: str
    resource_uri: str


class PatternAssessment(BehaviourModel):
    pattern_id: Identifier = Field(description="ID of a selected pattern in the current playbook; assess each selected pattern exactly once.")
    status: AssessmentStatus = Field(description="observed means evidence of the pattern; not_observed means assessed without a match; not_assessed means insufficient authorized context.")
    summary: str = Field(max_length=1000, description="Short factual summary; nonblank for observed and not_assessed. Empty is allowed only for not_observed. Never include secrets, transcripts or hidden reasoning.")
    evidence: tuple[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)], ...] = Field(max_length=3, description="Up to three minimal factual observations. Must be empty for not_assessed. No full transcripts, credentials or hidden reasoning.")

    @model_validator(mode="after")
    def validate_assessment(self) -> Self:
        if self.status != "not_observed" and not self.summary.strip():
            raise ValueError("Observed and unassessed patterns require a factual summary")
        if self.status == "not_assessed" and self.evidence:
            raise ValueError("Unassessed patterns cannot include evidence")
        return self


class SubmitDiagnosticReport(BehaviourModel):
    idempotency_key: UUID = Field(description="Generate one UUID before submission. After a lost receipt, retry only the identical payload with this same key. Keys are scoped to the authenticated caller.")
    configuration_revision: int = Field(ge=1, description="Current revision returned by the playbook resource or run_diagnostics prompt. Stale reports require reloading and reassessing, never relabeling old evidence.")
    playbook_id: Identifier = Field(description="Enabled playbook ID from umbod://agent-behaviour/playbooks. Read its current instructions before collecting a report.")
    trigger: Literal["user_requested", "proactive"] = Field(description="Use user_requested only for a genuine user-invoked flow. proactive requires administrator allow_proactive=true plus user/client permission; respect refusals.")
    assessments: tuple[PatternAssessment, ...] = Field(min_length=1, max_length=20, description="Exactly one assessment for every selected pattern, including not_assessed when context is unavailable. Combined compact UTF-8 submission must not exceed 32 KiB.")

    @model_validator(mode="after")
    def validate_submission(self) -> Self:
        ids = tuple(item.pattern_id for item in self.assessments)
        if len(set(ids)) != len(ids):
            raise ValueError("Assess each pattern exactly once")
        if len(self.model_dump_json().encode("utf-8")) > 32768:
            raise ValueError("Submission exceeds 32 KiB")
        return self


class DiagnosticReceipt(BehaviourModel):
    report_id: UUID
    received_at: AwareDatetime
    duplicate: bool


class DiagnosticReport(BehaviourModel):
    report_id: UUID
    received_at: AwareDatetime
    expires_at: AwareDatetime
    caller: CallerContext
    submission: SubmitDiagnosticReport
    instructions: DiagnosticInstructions


class ReportSummary(BehaviourModel):
    report_id: UUID
    received_at: AwareDatetime
    expires_at: AwareDatetime
    caller: CallerContext
    playbook_id: Identifier
    configuration_revision: int
    trigger: Literal["user_requested", "proactive"]
    observed_pattern_ids: tuple[Identifier, ...]


class ReportQuery(BehaviourModel):
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    playbook_id: Identifier | None = None
    pattern_id: Identifier | None = None
    status: AssessmentStatus | None = None


class ReportPage(BehaviourModel):
    items: tuple[ReportSummary, ...]
    total: int = Field(ge=0)
