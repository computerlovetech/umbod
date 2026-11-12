import secrets
import time

from collections.abc import AsyncIterator
from contextvars import ContextVar
from dataclasses import dataclass
from unittest.mock import Mock

import pytest_asyncio
from fastmcp import FastMCP
from fastmcp.server.auth import AuthContext
from mcp.server.request_state import RequestStateSecurity
from umbod.logging import create_application_failure_signal
from umbod.mcp.connectors.downstream_mcp.provider import _REQUEST_CONNECTOR_SCOPE

from tests.persistence_runtime import prepared_inmemory_runtime
from umbod.core.callers import (
    AuthenticationProvenance,
    CallerContext,
    CallerSnapshot,
    DeclaredIssuer,
    GroupMembership,
    SubjectIdentity,
)
from umbod.core.invocation import DatabaseApprovalNonceStore
from umbod.core.filesystem.models import Permission, Principal, PrincipalType
from umbod.core.filesystem.provisioning.models import RootBootstrapGrant, RootBootstrapSpec
from umbod.infrastructure import (
    InMemoryContentConfig, create_content_driver, create_filesystem_transactions, create_root_provisioning,
)
from umbod.core.filesystem.authorization import VerifiedIdentityResolver
from umbod.core.persistence import Database
from umbod.core.filesystem.content import ContentService, FilesystemContent
from umbod.core.filesystem.ports import ContentDriver, ByteStream
from umbod.core.filesystem.models import ContentRef, StorageKey
from umbod.core.filesystem.stores.discovery import DatabaseFilesystemAuthorizationReader
from umbod.mcp.filesystem import DatabaseFilesystemServiceFactory, register_filesystem_resources, register_filesystem_tools
from umbod.mcp.filesystem.approval import McpFilesystemDeletionApproval
from umbod.mcp.filesystem.authorization import FilesystemToolVisibility, FilesystemVisibilityMiddleware
from umbod.mcp.filesystem.runtime import FilesystemDiscoveryRuntime
from umbod.mcp.metrics.in_memory import InMemoryMcpMetricsRecorder
from umbod.mcp.tools import McpObservedToolRegistrar
from umbod.mcp.listeners import create_mcp_signals
from umbod.mcp.signals import McpInvocationPublisher


def caller_snapshot(
    subject: str, issuer: str, groups: tuple[str, ...], provenance: AuthenticationProvenance
) -> CallerSnapshot:
    return CallerSnapshot(
        caller=CallerContext(
            authentication=provenance,
            subject=SubjectIdentity(issuer=DeclaredIssuer(value=issuer), subject=subject),
        ),
        groups=GroupMembership(group_ids=groups),
    )


class ScopedCallerCapture:
    def __init__(self) -> None:
        self.current: ContextVar[CallerSnapshot] = ContextVar("filesystem_caller")
        self.count = 0

    def capture(self) -> CallerSnapshot:
        self.count += 1
        return self.current.get()


class RecordingContent:
    def __init__(self, delegate: ContentDriver) -> None:
        self.delegate = delegate
        self.put_count = 0

    async def put(self, data: ByteStream) -> ContentRef:
        self.put_count += 1
        return await self.delegate.put(data)

    def get(self, key: StorageKey) -> ByteStream:
        return self.delegate.get(key)


@dataclass
class FilesystemState:
    callers: ScopedCallerCapture
    metrics: InMemoryMcpMetricsRecorder
    services: DatabaseFilesystemServiceFactory
    content: RecordingContent
    files: FilesystemContent
    database: Database
    runtime: FilesystemDiscoveryRuntime
    visibility: FilesystemToolVisibility
    approval: McpFilesystemDeletionApproval


@dataclass
class FilesystemMcp(FilesystemState):
    server: FastMCP


class InvocationFilesystemToolVisibility(FilesystemToolVisibility):
    async def authorize(self, context: AuthContext) -> bool:
        return not _REQUEST_CONNECTOR_SCOPE.get()


@pytest_asyncio.fixture
async def filesystem_state() -> AsyncIterator[FilesystemState]:
    runtime = await prepared_inmemory_runtime()
    await create_root_provisioning(database=runtime.database).provision(
        RootBootstrapSpec(grants=(RootBootstrapGrant(
            principal=Principal(type=PrincipalType.GROUP, issuer="https://issuer", id="writers"),
            permissions=frozenset({Permission.DISCOVER, Permission.WRITE}),
        ),))
    )
    callers = ScopedCallerCapture()
    callers.current.set(caller_snapshot(
        "alice", "https://issuer", ("writers",), AuthenticationProvenance.UPSTREAM_VERIFIED
    ))
    metrics = InMemoryMcpMetricsRecorder()
    content = RecordingContent(create_content_driver(InMemoryContentConfig(type="inmemory")))
    services = DatabaseFilesystemServiceFactory(runtime.database, content, 20_971_520, "https://issuer", "https://api.example", max_read_bytes=1_048_576)
    files = ContentService(
        VerifiedIdentityResolver(), create_filesystem_transactions(database=runtime.database),
        content, 20_971_520,
    )
    discovery = FilesystemDiscoveryRuntime(DatabaseFilesystemAuthorizationReader(runtime.database))
    await discovery.reconcile()
    visibility = InvocationFilesystemToolVisibility(callers, discovery)
    approval = McpFilesystemDeletionApproval(
        nonce_store=DatabaseApprovalNonceStore(runtime.database),
        clock=time.time, random_token=lambda: secrets.token_urlsafe(24),
    )
    try:
        yield FilesystemState(callers, metrics, services, content, files, runtime.database, discovery, visibility, approval)
    finally:
        await runtime.shutdown()


def create_filesystem_server(state: FilesystemState, filtered: bool) -> FilesystemMcp:
    application_failures = create_application_failure_signal()
    server = FastMCP(request_state_security=RequestStateSecurity(
        keys=[secrets.token_urlsafe(48)], ttl=300.0, audience="filesystem-delete-test",
    ))
    visibility = FilesystemToolVisibility(state.callers, state.runtime) if filtered else state.visibility
    if filtered:
        server.add_middleware(FilesystemVisibilityMiddleware(visibility))
    register_filesystem_tools(
        McpObservedToolRegistrar(server, McpInvocationPublisher(create_mcp_signals(Mock(), state.metrics, Mock(), application_failures=application_failures))),
        state.callers, state.services, visibility, state.approval,
    )
    register_filesystem_resources(server, state.callers, state.services)
    return FilesystemMcp(
        callers=state.callers, metrics=state.metrics, services=state.services, content=state.content,
        files=state.files, database=state.database, runtime=state.runtime, visibility=visibility,
        approval=state.approval, server=server,
    )


@pytest_asyncio.fixture
async def filesystem_mcp(filesystem_state: FilesystemState) -> FilesystemMcp:
    return create_filesystem_server(filesystem_state, filtered=True)


@pytest_asyncio.fixture
async def filesystem_invocation_mcp(filesystem_state: FilesystemState) -> FilesystemMcp:
    return create_filesystem_server(filesystem_state, filtered=False)
