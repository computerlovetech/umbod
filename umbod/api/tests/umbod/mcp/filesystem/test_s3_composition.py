import pytest

from tests.mcp_fixtures import build_test_mcp
from umbod.config import AppConfig
from umbod.core.filesystem import ContentDriver
from umbod.infrastructure import (
    ContentConfig,
    InMemoryContentConfig,
    S3ContentConfig,
    create_content_driver,
)
from umbod.mcp import public_app
from umbod.mcp.filesystem import DatabaseFilesystemServiceFactory
from umbod.mcp.filesystem.caller import CurrentFilesystemCallerCapture
from umbod.mcp.tools import McpObservedToolRegistrar


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint,prefix,style", [
    ("", "", "auto"), ("http://minio:9000", "umbod/content", "path"),
])
async def test_mcp_composes_s3_once_and_retains_operation_scoped_services(
    monkeypatch: pytest.MonkeyPatch, endpoint: str, prefix: str, style: str,
) -> None:
    selected: list[ContentConfig] = []
    captured: list[DatabaseFilesystemServiceFactory] = []
    content = create_content_driver(InMemoryContentConfig(type="inmemory"))
    register_tools = public_app.register_filesystem_tools

    def fake_content_factory(config: ContentConfig) -> ContentDriver:
        selected.append(config)
        return content

    def capture_registration(
        registrar: McpObservedToolRegistrar, callers: CurrentFilesystemCallerCapture,
        services: DatabaseFilesystemServiceFactory,
    ) -> None:
        captured.append(services)
        register_tools(registrar, callers, services)

    monkeypatch.setattr(public_app, "create_content_driver", fake_content_factory)
    monkeypatch.setattr(public_app, "register_filesystem_tools", capture_registration)
    settings = AppConfig(filesystem={"content": {
        "type": "s3", "bucket": "umbod-content", "region": "us-east-1",
        "endpoint_url": endpoint, "prefix": prefix, "addressing_style": style,
    }})
    server = await build_test_mcp(settings=settings, connector_registrations=[])
    try:
        assert len(selected) == 1
        assert isinstance(selected[0], S3ContentConfig)
        assert selected[0].model_dump() == settings.filesystem.content.model_dump()
        assert len(captured) == 1
        services = captured[0]
        assert services.uploads() is not services.uploads()
        assert services.content() is not services.content()
        assert len(selected) == 1
    finally:
        await server.persistence_runtime.shutdown()
