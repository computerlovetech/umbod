from typing import Any

from fastmcp.tools import Tool, ToolResult
from pydantic import PrivateAttr, ValidationError

from umbod.build_identity import UMBOD_RELEASE, UMBOD_REVISION
from umbod.core.agent_behaviour import AgentBehaviourError, AgentBehaviourService, DiagnosticReceipt, StorageUnavailable, SubmitDiagnosticReport
from umbod.core.responses import OperationState, RetryAdvice, ToolErrorDetails, ToolResponseMetadataFactory
from umbod.http_metadata import current_request_id
from umbod.mcp.responses.adapter import BuiltinToolResult, RESPONSE_METADATA_KEY
from umbod.mcp.responses.progress import operation_completed, operation_started
from umbod.mcp.responses.rendering import render_failure_guidance

from .authorization import DiagnosticCallerPolicy

REPORT_DESCRIPTION = (
    "Submit a durable agent self-report, not independently verified evidence. First read current instructions from "
    "umbod://agent-behaviour/playbooks/{playbook_id} or use run_diagnostics to start the flow. "
    "Use only authorized context, respect user and client policy and refusals, and describe how diagnostics began "
    "in trigger; it is caller-reported metadata, not permission. "
    "Use configuration_revision and playbook_id from those instructions and assess every selected pattern exactly once. "
    "Generate one UUID idempotency_key before submission. After storage failure or a lost response, retry only the "
    "identical payload with that same UUID, never a new key. Do not claim success until a receipt returns. "
    "Never send transcripts, secrets, credentials or hidden reasoning. Use short factual summaries and at most three "
    "evidence strings per assessment; not_assessed needs a nonblank summary and no evidence. "
    "Summaries are at most 1000 characters, evidence strings at most 500, and compact UTF-8 submission JSON at most 32 KiB."
)
EXACT_RETRY = "If a response was lost or persistence may have committed, retry only the identical payload with the same idempotency_key. Never generate a replacement key; deduplication makes this exact retry safe."
CORRECTIONS = {
    "stale_configuration": "Reload current instructions and reassess; never silently relabel old evidence with a new revision.",
    "reporting_disabled": "Reporting is disabled. Do not submit reports while it is off; rediscover the tool after an administrator re-enables it.",
    "idempotency_conflict": "This key belongs to a different submission. Do not change or replay it; reconcile the original submission first.",
    "report_gone": "The report was deleted. Do not attempt to resurrect it or generate a replacement key.",
    "unauthorized": "Authenticate with an eligible MCP identity before requesting diagnostics.",
    "instructions_unavailable": "Select an enabled playbook from the current playbook index before collecting diagnostics.",
    "report_invalid": "Correct the submission to match the published schema and include every selected pattern exactly once.",
}


def diagnostic_failure(code: str, uncertain: bool) -> BuiltinToolResult:
    instruction = EXACT_RETRY if uncertain else CORRECTIONS.get(code, "Correct the submission before retrying.")
    known_retry = RetryAdvice.NEVER if code == "reporting_disabled" else RetryAdvice.AFTER_CORRECTION
    metadata = ToolResponseMetadataFactory(UMBOD_RELEASE, UMBOD_REVISION).failure(
        current_request_id() or "diagnostic-report",
        error=ToolErrorDetails(code=code, message="Diagnostic report was not acknowledged.", issues=()),
        operation_state=OperationState.UNKNOWN if uncertain else OperationState.NOT_STARTED,
        retry=RetryAdvice.INSPECT_BEFORE_RETRY if uncertain else known_retry,
        instructions=(instruction,), notices=(),
    )
    return BuiltinToolResult(content=render_failure_guidance(metadata), is_error=True,
                             meta={RESPONSE_METADATA_KEY: metadata.model_dump(mode="json")})


def report_input_schema() -> dict[str, Any]:
    schema = SubmitDiagnosticReport.model_json_schema()
    descriptions = {
        "idempotency_key": "Generate one UUID before submission; preserve it and the identical payload on any uncertain retry.",
        "configuration_revision": "Use the current instruction revision. Stale instructions require reloading and reassessment, not relabeling evidence.",
        "playbook_id": "Enabled playbook ID from the current diagnostic instruction resource.",
        "trigger": "Caller-reported metadata: user_requested when requested by the user, or proactive when initiated without a user request. This field does not grant permission.",
        "assessments": "Every selected pattern exactly once, with unique pattern IDs; assessment order is insignificant for idempotency.",
    }
    for name, description in descriptions.items():
        schema["properties"][name]["description"] = description
    assessment = schema["$defs"]["PatternAssessment"]["properties"]
    assessment["status"]["description"] = "Agent self-report, not verified evidence. Use not_assessed when authorized factual context is unavailable."
    assessment["summary"]["description"] = "Short factual summary; nonblank for observed and not_assessed, empty allowed for not_observed. Never include hidden reasoning or secrets."
    assessment["evidence"]["description"] = "Zero to three short factual strings; forbidden for not_assessed. Never include transcripts, secrets or credentials. Evidence order is preserved."
    return schema


class DiagnosticReportTool(Tool):
    _service: AgentBehaviourService = PrivateAttr()
    _policy: DiagnosticCallerPolicy = PrivateAttr()

    def __init__(self, service: AgentBehaviourService, policy: DiagnosticCallerPolicy) -> None:
        super().__init__(name="report_diagnostic", description=REPORT_DESCRIPTION,
                         parameters=report_input_schema(),
                         output_schema=DiagnosticReceipt.model_json_schema(), auth=policy.authorize)
        self._service = service
        self._policy = policy

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            caller = self._policy.require()
            command = SubmitDiagnosticReport.model_validate(arguments)
        except AgentBehaviourError as error:
            return diagnostic_failure(error.code, False)
        except ValidationError:
            return diagnostic_failure("report_invalid", False)
        operation_started()
        try:
            receipt = await self._service.submit_report(caller, command)
        except StorageUnavailable:
            return diagnostic_failure("storage_unavailable", True)
        except AgentBehaviourError as error:
            return diagnostic_failure(error.code, False)
        except Exception:
            return diagnostic_failure("storage_unavailable", True)
        operation_completed()
        return ToolResult(structured_content=receipt.model_dump(mode="json"))
