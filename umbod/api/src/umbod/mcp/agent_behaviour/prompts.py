from fastmcp.exceptions import PromptError
from fastmcp.prompts import Message

from umbod.core.agent_behaviour import AgentBehaviourError, AgentBehaviourService

from .authorization import DiagnosticCallerPolicy


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
        return [Message(
            f"Read the current Umbod MCP resource `{instructions.resource_uri}` and follow its reporting guidance. "
            "If you cannot read the resource, stop without submitting. Reading this prompt does not grant "
            "permission or submit a report.",
            role="user",
        )]
