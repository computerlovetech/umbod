import json

from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError

from umbod.core.agent_behaviour import AgentBehaviourError, AgentBehaviourService, InstructionsUnavailable, available_playbooks
from umbod.core.agent_behaviour.policy import require_reporting_enabled

from .authorization import DiagnosticCallerPolicy

PLAYBOOK_INDEX = "umbod://agent-behaviour/playbooks"
PLAYBOOK_TEMPLATE = PLAYBOOK_INDEX + "/{playbook_id}"


def is_playbook_uri(uri: str) -> bool:
    return uri == PLAYBOOK_INDEX or uri.startswith(f"{PLAYBOOK_INDEX}/")


class DiagnosticResources:
    def __init__(self, service: AgentBehaviourService, policy: DiagnosticCallerPolicy) -> None:
        self._service = service
        self._policy = policy

    async def index(self) -> str:
        try:
            self._policy.require()
            configuration = await self._service.get_configuration()
            require_reporting_enabled(configuration)
            playbooks = available_playbooks(configuration)
            if not playbooks:
                raise InstructionsUnavailable()
        except AgentBehaviourError as error:
            raise ResourceError(error.code) from None
        return json.dumps({
            "configuration_revision": configuration.revision,
            "playbooks": [
                {"id": playbook.id, "name": playbook.name,
                 "resource_uri": f"{PLAYBOOK_INDEX}/{playbook.id}"}
                for playbook in playbooks
            ],
        }, ensure_ascii=False)

    async def instructions(self, playbook_id: str) -> str:
        try:
            self._policy.require()
            return (await self._service.get_instructions(playbook_id)).model_dump_json()
        except AgentBehaviourError as error:
            raise ResourceError(error.code) from None


def register_resources(server: FastMCP, resources: DiagnosticResources, policy: DiagnosticCallerPolicy) -> None:
    server.resource(PLAYBOOK_INDEX, name="diagnostic_playbooks", mime_type="application/json", auth=policy.authorize)(resources.index)
    server.resource(PLAYBOOK_TEMPLATE, name="diagnostic_instructions", mime_type="application/json", auth=policy.authorize)(resources.instructions)
