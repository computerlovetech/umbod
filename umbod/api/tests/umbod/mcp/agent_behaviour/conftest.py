from collections.abc import AsyncIterator
from contextvars import ContextVar
from dataclasses import dataclass
from unittest.mock import Mock

import pytest_asyncio
from fastmcp import FastMCP

from tests.persistence_runtime import prepared_inmemory_runtime
from umbod.core.agent_behaviour import AgentBehaviourService, BehaviourPattern, DiagnosticPlaybook, PublishConfiguration, create_agent_behaviour_service
from umbod.core.callers import AuthenticationProvenance, CallerContext, DeclaredIssuer, SubjectIdentity
from umbod.logging import create_application_failure_signal
from umbod.mcp.agent_behaviour.composition import register_agent_behaviour
from umbod.mcp.listeners import create_mcp_signals
from tests.support import InMemoryMcpMetricsRecorder
from umbod.mcp.signals import McpInvocationPublisher
from umbod.mcp.tools import McpObservedToolRegistrar


class TestCallerCapture:
    __test__ = False

    def __init__(self) -> None:
        self.current: ContextVar[CallerContext] = ContextVar("diagnostic-test-caller")
        self.current.set(CallerContext(authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
                                       subject=SubjectIdentity(issuer=DeclaredIssuer(value="https://identity.invalid"), subject="alice")))

    def capture(self) -> CallerContext:
        return self.current.get()


@dataclass
class DiagnosticMcp:
    server: FastMCP
    service: AgentBehaviourService
    callers: TestCallerCapture
    observations: Mock


def create_diagnostic_server(service: AgentBehaviourService, callers: TestCallerCapture, observations: Mock) -> FastMCP:
    server = FastMCP()
    signals = create_mcp_signals(observations, InMemoryMcpMetricsRecorder(), Mock(), application_failures=create_application_failure_signal())
    register_agent_behaviour(server, McpObservedToolRegistrar(server, McpInvocationPublisher(signals)), service, callers, allow_local=False)
    return server


@pytest_asyncio.fixture
async def default_diagnostic_mcp() -> AsyncIterator[DiagnosticMcp]:
    runtime = await prepared_inmemory_runtime()
    try:
        service = create_agent_behaviour_service(runtime.database)
        callers = TestCallerCapture()
        observations = Mock()
        server = create_diagnostic_server(service, callers, observations)
        yield DiagnosticMcp(server, service, callers, observations)
    finally:
        await runtime.shutdown()


@pytest_asyncio.fixture
async def diagnostic_mcp(default_diagnostic_mcp: DiagnosticMcp) -> DiagnosticMcp:
    pattern = BehaviourPattern(id="fallback", name="Fallback", description="Factual fallback", assessment_prompt="Assess fallback", inclusion_criteria="Unavailable context", exclusion_criteria="Normal clarification", categories=(), polarity="neutral", enabled=True)
    playbook = DiagnosticPlaybook(id="review", name="Review", collection_instructions="Review available authorized facts", pattern_ids=(pattern.id,), enabled=True)
    await default_diagnostic_mcp.service.publish_configuration(PublishConfiguration(reporting_enabled=True, expected_revision=1, patterns=(pattern,), playbooks=(playbook,)))
    return default_diagnostic_mcp
