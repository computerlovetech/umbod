from fastmcp.exceptions import PromptError
from fastmcp.prompts import Message

from umbod.core.agent_behaviour import AgentBehaviourError, AgentBehaviourService

from .authorization import DiagnosticCallerPolicy

PROMPT_ENVELOPE = (
    "This is a user-requested diagnostic assessment, not independent verification. "
    "Slash-command presentation depends on the MCP client. Reading this prompt does not submit a report or create a session. "
    "The server-owned reporting_guidance below takes precedence over configurable collection text. "
    "Only assess available authorized context; respect exclusions and user/client refusal. "
    "Never gather external data or run tools solely for diagnostics without user authority. "
    "Never submit transcripts, secrets, credentials, or hidden reasoning; use short factual summaries. "
    "Do not infer facts. Mark unavailable patterns not_assessed with a nonblank summary and no evidence. "
    "Call report_diagnostic with a newly generated UUID idempotency_key, the supplied configuration_revision, "
    "playbook_id, trigger=user_requested, and assessments containing every selected pattern exactly once. "
    "Each assessment has pattern_id, status (observed, not_observed, not_assessed), summary, and evidence (at most three factual strings). "
    "Observed summaries must be nonblank. Proactive calls require allow_proactive=true and user/client authority. "
    "No report succeeds until a durable receipt returns. After a lost response or storage failure retry only the identical "
    "payload with the same UUID; never generate a replacement key. On stale_configuration reload and reassess, "
    "never relabel earlier evidence with a new revision. Correct invalid/gated submissions rather than automatically retrying. "
    "Resolved current instructions follow as JSON:\n"
)


class DiagnosticPrompts:
    def __init__(self, service: AgentBehaviourService, policy: DiagnosticCallerPolicy) -> None:
        self._service = service
        self._policy = policy

    async def run_diagnostics(self, playbook_id: str) -> list[Message]:
        try:
            self._policy.require()
            instructions = await self._service.get_instructions(playbook_id)
        except AgentBehaviourError as error:
            raise PromptError(error.code) from None
        return [Message(PROMPT_ENVELOPE + instructions.model_dump_json(), role="user")]
