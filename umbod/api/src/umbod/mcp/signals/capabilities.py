from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

from umbod.core.invocation.failure_evidence import InvocationExceptionEvidence, InvocationFailureEvidence
from umbod.mcp.signals.events import McpInvocationActor, McpInvocationCorrelation


class McpCapabilityMethod(StrEnum):
    READ_RESOURCE = "resources/read"
    GET_PROMPT = "prompts/get"
    LIST_RESOURCES = "resources/list"
    LIST_RESOURCE_TEMPLATES = "resources/templates/list"
    LIST_PROMPTS = "prompts/list"


class McpCapabilityOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"


class McpCapabilityFailureCategory(StrEnum):
    AUTHORIZATION = "authorization"
    VALIDATION = "validation"
    NOT_FOUND = "not_found"
    UNEXPECTED_ERROR = "unexpected_error"


@dataclass(frozen=True)
class McpCapabilityDiscoveryTarget:
    pass


@dataclass(frozen=True)
class McpResourceTarget:
    uri_fingerprint: str


@dataclass(frozen=True)
class McpPromptTarget:
    name_fingerprint: str


McpCapabilityTarget = McpCapabilityDiscoveryTarget | McpResourceTarget | McpPromptTarget


def resource_target(uri: str) -> McpResourceTarget:
    return McpResourceTarget(sha256(b"mcp.resource.uri\x00" + uri.encode("utf-8", errors="replace")).hexdigest())


def prompt_target(name: str) -> McpPromptTarget:
    return McpPromptTarget(sha256(b"mcp.prompt.name\x00" + name.encode("utf-8", errors="replace")).hexdigest())


@dataclass(frozen=True)
class McpCapabilitySucceeded:
    @property
    def outcome(self) -> McpCapabilityOutcome:
        return McpCapabilityOutcome.SUCCESS


@dataclass(frozen=True)
class McpCapabilityFailed:
    category: McpCapabilityFailureCategory
    evidence: InvocationFailureEvidence

    @property
    def outcome(self) -> McpCapabilityOutcome:
        return McpCapabilityOutcome.FAILURE


@dataclass(frozen=True)
class McpCapabilityCancelled:
    evidence: InvocationExceptionEvidence

    @property
    def outcome(self) -> McpCapabilityOutcome:
        return McpCapabilityOutcome.CANCELLED


McpCapabilityResult = McpCapabilitySucceeded | McpCapabilityFailed | McpCapabilityCancelled


@dataclass(frozen=True)
class McpCapabilityCompleted:
    method: McpCapabilityMethod
    target: McpCapabilityTarget
    result: McpCapabilityResult
    duration_ms: float
    correlation: McpInvocationCorrelation
    actor: McpInvocationActor
    started_at_unix_nano: int

    @property
    def outcome(self) -> McpCapabilityOutcome:
        return self.result.outcome
