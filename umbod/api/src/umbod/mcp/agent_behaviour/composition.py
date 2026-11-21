from fastmcp import FastMCP

from umbod.core.agent_behaviour import AgentBehaviourService, create_agent_behaviour_service
from umbod.core.persistence import Database
from umbod.mcp.tools import McpObservedToolRegistrar
from umbod.mcp.tools.registration import tool_result_is_error

from .authorization import DiagnosticCallerPolicy
from .caller import CurrentDiagnosticCallerCapture, DiagnosticCallerCapture
from .prompts import DiagnosticPrompts
from .resources import DiagnosticResources, register_resources
from .tools import DiagnosticReportTool
from .visibility import DiagnosticVisibilityMiddleware


def register_agent_behaviour(
    server: FastMCP, registrar: McpObservedToolRegistrar,
    service: AgentBehaviourService, callers: DiagnosticCallerCapture, *, allow_local: bool,
) -> None:
    policy = DiagnosticCallerPolicy(callers, allow_local)
    tool = registrar.register_tool(DiagnosticReportTool(service, policy), result_is_error=tool_result_is_error,
                                   operation_names=frozenset(), builtin_response=True)
    register_resources(server, DiagnosticResources(service, policy), policy)
    server.prompt(name="run_diagnostics", description="Run user-requested diagnostics using the selected live playbook resource. Slash-command presentation is client-dependent.", auth=policy.authorize)(DiagnosticPrompts(service, policy).run_diagnostics)
    server.add_middleware(DiagnosticVisibilityMiddleware(policy, tool))


def register_configured_agent_behaviour(
    server: FastMCP, registrar: McpObservedToolRegistrar, database: Database, *, allow_local: bool,
) -> AgentBehaviourService:
    service = create_agent_behaviour_service(database)
    register_agent_behaviour(server, registrar, service, CurrentDiagnosticCallerCapture(server), allow_local=allow_local)
    return service
