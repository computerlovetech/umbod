from collections.abc import AsyncIterator
from contextvars import ContextVar
from dataclasses import dataclass
from unittest.mock import Mock

import pytest_asyncio
from fastmcp import FastMCP

from tests.persistence_runtime import prepared_inmemory_runtime
from umbod.core.callers import (
    AuthenticationProvenance,
    CallerContext,
    CallerSnapshot,
    DeclaredIssuer,
    GroupMembership,
    SubjectIdentity,
)
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
from umbod.mcp.filesystem import DatabaseFilesystemServiceFactory, register_filesystem_tools
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
class FilesystemMcp:
    server: FastMCP
    callers: ScopedCallerCapture
    metrics: InMemoryMcpMetricsRecorder
    services: DatabaseFilesystemServiceFactory
    content: RecordingContent
    files: FilesystemContent
    database: Database


@pytest_asyncio.fixture
async def filesystem_mcp() -> AsyncIterator[FilesystemMcp]:
    runtime = await prepared_inmemory_runtime()
    await create_root_provisioning(database=runtime.database).provision(
        RootBootstrapSpec(grants=(RootBootstrapGrant(
            principal=Principal(type=PrincipalType.GROUP, issuer="https://issuer", id="writers"),
            permissions=frozenset({Permission.DISCOVER, Permission.WRITE}),
        ),))
    )
    server = FastMCP()
    callers = ScopedCallerCapture()
    callers.current.set(caller_snapshot(
        "alice", "https://issuer", ("writers",), AuthenticationProvenance.UPSTREAM_VERIFIED
    ))
    metrics = InMemoryMcpMetricsRecorder()
    content = RecordingContent(create_content_driver(InMemoryContentConfig(type="inmemory")))
    services = DatabaseFilesystemServiceFactory(runtime.database, content, 20_971_520)
    files = ContentService(
        VerifiedIdentityResolver(), create_filesystem_transactions(database=runtime.database),
        content, 20_971_520,
    )
    register_filesystem_tools(
        McpObservedToolRegistrar(server, McpInvocationPublisher(create_mcp_signals(Mock(), metrics, Mock()))),
        callers,
        services,
    )
    try:
        yield FilesystemMcp(server, callers, metrics, services, content, files, runtime.database)
    finally:
        await runtime.shutdown()
