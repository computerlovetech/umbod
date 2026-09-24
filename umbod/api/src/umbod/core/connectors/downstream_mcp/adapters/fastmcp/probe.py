import asyncio
from typing import Iterator
from urllib.parse import SplitResult, urljoin, urlsplit

import httpx2
from mcp.types import Prompt, Resource, ResourceTemplate, Tool

from umbod.core.connectors.downstream_mcp.models import (
    DiscoveredPrompt,
    DiscoveredResource,
    DiscoveredResourceTemplate,
    DiscoveredServerIcon,
    PromptArgument,
)
from umbod.core.connectors.downstream_mcp.probe import (
    DiscoveredCapabilities,
    DiscoveredCapabilityTool,
    DownstreamConnectorValidationError,
    ProbeCapabilities,
    ProbeFailed,
    ProbeResult,
)

from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth import SignInRequired
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.connection import (
    FastMCPConnectionFactory,
    FastMCPConnectionStrategy,
    TlsVerification,
)
from umbod.core.connectors.downstream_mcp.connection import (
    DownstreamMcpConnectionConfiguration,
)


class FastMCPDownstreamConnection:
    def __init__(
        self,
        tls_verification: TlsVerification,
        timeout_seconds: float,
        connection_factory: FastMCPConnectionFactory,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("probe timeout must be positive")
        self._timeout_seconds = timeout_seconds
        self.connection_factory = connection_factory

    async def probe(
        self, configuration: DownstreamMcpConnectionConfiguration
    ) -> ProbeResult:
        try:
            connection = self.connection_factory.create(configuration)
        except Exception as error:
            return self._classify_exception(error)
        return await _DownstreamMcpProbeSession(
            self, self.connection_factory, connection
        ).run()

    @classmethod
    def _safe_redirect_url(cls, current_url: str, response: httpx2.Response) -> str | None:
        location = response.headers.get("location")
        if location is None:
            return None
        try:
            target_url = urljoin(current_url, location)
            current = urlsplit(current_url)
            target = urlsplit(target_url)
            current.port
            target.port
        except ValueError:
            return None
        if target.username is not None or target.password is not None or target.fragment:
            return None
        if cls._origin(current) == cls._origin(target):
            return target_url
        if not cls._is_proxy_trailing_slash_redirect(current, target):
            return None
        return target._replace(scheme="https").geturl()

    @classmethod
    def _is_proxy_trailing_slash_redirect(cls, current: SplitResult, target: SplitResult) -> bool:
        if current.scheme != "https" or target.scheme != "http":
            return False
        https_target = target._replace(scheme="https")
        if cls._origin(current) != cls._origin(https_target):
            return False
        if current.path.endswith("/") or target.path != f"{current.path}/":
            return False
        return target.query == current.query

    @staticmethod
    def _origin(parsed: SplitResult) -> tuple[str, str, int]:
        hostname = parsed.hostname or ""
        port = parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)
        return parsed.scheme, hostname, port

    @staticmethod
    def _map_tool(tool: Tool) -> DiscoveredCapabilityTool:
        return DiscoveredCapabilityTool(name=tool.name, title=tool.title or tool.name, description=tool.description or "", input_schema=tool.input_schema, output_schema=tool.output_schema, annotations=tool.annotations.model_dump(by_alias=True, exclude_none=True) if tool.annotations is not None else {}, icons=tuple(icon.model_dump(by_alias=True, exclude_none=True) for icon in tool.icons or ()), meta=tool.meta or {}, execution=tool.execution.model_dump(by_alias=True, exclude_none=True) if tool.execution is not None else {})

    @staticmethod
    def _map_prompt(prompt: Prompt) -> DiscoveredPrompt:
        return DiscoveredPrompt(name=prompt.name, title=prompt.title or prompt.name, description=prompt.description or "", arguments=tuple(PromptArgument(name=item.name, title=item.title or "", description=item.description or "", required=item.required or False) for item in prompt.arguments or ()), icons=tuple(icon.model_dump(by_alias=True, exclude_none=True) for icon in prompt.icons or ()), meta=prompt.meta or {})

    @staticmethod
    def _map_resource(resource: Resource) -> DiscoveredResource:
        return DiscoveredResource(name=resource.name, title=resource.title or resource.name, uri=str(resource.uri), description=resource.description or "", mime_type=resource.mime_type or "", size=resource.size or 0, icons=tuple(icon.model_dump(by_alias=True, exclude_none=True) for icon in resource.icons or ()), annotations=resource.annotations.model_dump(by_alias=True, exclude_none=True) if resource.annotations is not None else {}, meta=resource.meta or {})

    @staticmethod
    def _map_template(template: ResourceTemplate) -> DiscoveredResourceTemplate:
        return DiscoveredResourceTemplate(name=template.name, title=template.title or template.name, uri_template=template.uri_template, description=template.description or "", mime_type=template.mime_type or "", icons=tuple(icon.model_dump(by_alias=True, exclude_none=True) for icon in template.icons or ()), annotations=template.annotations.model_dump(by_alias=True, exclude_none=True) if template.annotations is not None else {}, meta=template.meta or {})

    @staticmethod
    def _exception_chain(error: BaseException) -> Iterator[BaseException]:
        pending = [error]
        visited_exception_ids: set[int] = set()
        while pending:
            current = pending.pop()
            if id(current) in visited_exception_ids:
                continue
            visited_exception_ids.add(id(current))
            yield current
            if isinstance(current, BaseExceptionGroup):
                pending.extend(current.exceptions)
            cause = current.__cause__ or current.__context__
            if cause is not None:
                pending.append(cause)

    @classmethod
    def _response_from_exception(cls, error: BaseException) -> httpx2.Response | None:
        for current in cls._exception_chain(error):
            response = getattr(current, "response", None)
            if isinstance(response, httpx2.Response):
                return response
        return None

    def _classify_exception(self, error: BaseException) -> ProbeFailed:
        response = self._response_from_exception(error)
        if response is not None:
            if response.status_code == 404:
                return ProbeFailed(code="endpoint_not_found")
            if response.status_code in (401, 403):
                return ProbeFailed(code="auth_rejected")
            return ProbeFailed(code="invalid_mcp_protocol")
        for current in self._exception_chain(error):
            if isinstance(current, SignInRequired):
                return ProbeFailed(code="auth_rejected")
            if isinstance(current, DownstreamConnectorValidationError):
                return ProbeFailed(code=current.code)
            if isinstance(current, httpx2.TimeoutException):
                return ProbeFailed(code="timeout")
            if isinstance(current, httpx2.TransportError):
                return ProbeFailed(code="unreachable")
        return ProbeFailed(code="invalid_mcp_protocol")


async def _empty_catalog() -> list:
    return []


class _DownstreamMcpProbeSession:
    _MAX_REDIRECTS = 6

    def __init__(
        self,
        probe: FastMCPDownstreamConnection,
        connection_factory: FastMCPConnectionFactory,
        connection: FastMCPConnectionStrategy,
    ) -> None:
        self._probe = probe
        self._connection_factory = connection_factory
        self._connection = connection

    async def run(self) -> ProbeResult:
        current_configuration = self._connection.configuration
        for redirect_count in range(self._MAX_REDIRECTS):
            try:
                return await self._collect_capabilities()
            except TimeoutError:
                return ProbeFailed(code="timeout")
            except Exception as error:
                redirected_configuration = self._follow_redirect(
                    current_configuration, error, redirect_count
                )
                if redirected_configuration is None:
                    return self._probe._classify_exception(error)
                if isinstance(redirected_configuration, ProbeFailed):
                    return redirected_configuration
                current_configuration = redirected_configuration
                try:
                    self._connection = self._connection_factory.create(
                        redirected_configuration
                    )
                except Exception as redirected_error:
                    return self._probe._classify_exception(redirected_error)
        return ProbeFailed(code="redirect_limit_exceeded")

    async def _collect_capabilities(self) -> ProbeCapabilities:
        connection = self._connection
        async with asyncio.timeout(self._probe._timeout_seconds):
            client = connection.create_client()
            async with client:
                capabilities = client.server_capabilities
                if capabilities is None:
                    raise ValueError("Missing negotiated MCP capabilities")
                # Features are optional: asking a tools-only server for prompts
                # or resources can legitimately return Method not found.
                tools, prompts, resources, templates = await asyncio.gather(
                    client.list_tools() if capabilities.tools is not None else _empty_catalog(),
                    client.list_prompts() if capabilities.prompts is not None else _empty_catalog(),
                    client.list_resources() if capabilities.resources is not None else _empty_catalog(),
                    client.list_resource_templates() if capabilities.resources is not None else _empty_catalog(),
                )
                server_info = client.server_info
        server_icons = (
            server_info.icons or ()
            if server_info is not None
            else ()
        )
        return ProbeCapabilities(
            endpoint_url=connection.configuration.endpoint_url,
            oauth_authorization=connection.export_authorization(client),
            capabilities=DiscoveredCapabilities(
                tools=tuple(self._probe._map_tool(tool) for tool in tools),
                server_icons=tuple(
                    DiscoveredServerIcon(
                        src=icon.src,
                        mime_type=icon.mime_type or "",
                        sizes=tuple(icon.sizes or ()),
                        theme=icon.theme or "",
                    )
                    for icon in server_icons
                ),
                prompts=tuple(self._probe._map_prompt(prompt) for prompt in prompts),
                resources=tuple(self._probe._map_resource(resource) for resource in resources),
                resource_templates=tuple(
                    self._probe._map_template(template) for template in templates
                ),
            ),
        )

    def _follow_redirect(
        self,
        configuration: DownstreamMcpConnectionConfiguration,
        error: BaseException,
        redirect_count: int,
    ) -> DownstreamMcpConnectionConfiguration | ProbeFailed | None:
        response = self._probe._response_from_exception(error)
        if response is None or not response.is_redirect:
            return None
        if redirect_count == self._MAX_REDIRECTS - 1:
            return ProbeFailed(code="redirect_limit_exceeded")
        redirected_url = self._probe._safe_redirect_url(
            str(configuration.endpoint_url),
            response,
        )
        if redirected_url is None:
            return ProbeFailed(code="unsafe_redirect")
        return configuration.model_copy(update={"endpoint_url": redirected_url})
