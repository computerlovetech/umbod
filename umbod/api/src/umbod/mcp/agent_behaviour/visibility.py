from typing import Any

from fastmcp.exceptions import PromptError, ResourceError, ToolError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools import Tool

from umbod.core.agent_behaviour import AgentBehaviourService, CallerNotAuthorized, StorageUnavailable, available_playbooks

from .authorization import DiagnosticCallerPolicy
from .resources import is_playbook_uri


class DiagnosticVisibilityMiddleware(Middleware):
    def __init__(self, policy: DiagnosticCallerPolicy, tool: Tool, service: AgentBehaviourService) -> None:
        self._policy = policy
        self._tool = tool
        self._service = service

    def _eligible(self) -> bool:
        try:
            self._policy.require()
        except CallerNotAuthorized:
            return False
        return True

    async def _discoverable(self) -> bool:
        if not self._eligible():
            return False
        try:
            return bool(available_playbooks(await self._service.get_configuration()))
        except StorageUnavailable:
            return False

    async def on_list_tools(self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]) -> Any:
        tools = await call_next(context)
        discoverable = await self._discoverable()
        return [tool for tool in tools if tool.name != "report_diagnostic" or (discoverable and tool is self._tool)]

    async def on_list_prompts(self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]) -> Any:
        prompts = await call_next(context)
        discoverable = await self._discoverable()
        return [prompt for prompt in prompts if prompt.name != "run_diagnostics" or discoverable]

    async def on_list_resources(self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]) -> Any:
        resources = await call_next(context)
        discoverable = await self._discoverable()
        return [resource for resource in resources if not is_playbook_uri(str(resource.uri)) or discoverable]

    async def on_list_resource_templates(self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]) -> Any:
        templates = await call_next(context)
        discoverable = await self._discoverable()
        return [template for template in templates if not is_playbook_uri(template.uri_template) or discoverable]

    async def on_call_tool(self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]) -> Any:
        if context.message.name == "report_diagnostic":
            if not self._eligible():
                raise ToolError("unauthorized")
            runtime = context.fastmcp_context
            if runtime is None or await runtime.fastmcp.get_tool("report_diagnostic") is not self._tool:
                raise ToolError("instructions_unavailable")
        return await call_next(context)

    async def on_get_prompt(self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]) -> Any:
        if context.message.name == "run_diagnostics" and not self._eligible():
            raise PromptError("unauthorized")
        return await call_next(context)

    async def on_read_resource(self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]) -> Any:
        if is_playbook_uri(str(context.message.uri)) and not self._eligible():
            raise ResourceError("unauthorized")
        return await call_next(context)
