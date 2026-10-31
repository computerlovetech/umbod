import pytest

from tests.persistence_runtime import prepared_inmemory_runtime
from umbod.config import AppConfig
from umbod.core.filesystem import ContentDriver
from umbod.core.filesystem.authorization import VerifiedIdentityResolver
from umbod.core.filesystem.uploads import SystemUploadClock
from umbod.infrastructure import (
    ContentConfig,
    InMemoryContentConfig,
    S3ContentConfig,
    create_content_driver,
)
from umbod.rest import factories as factory_module
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.filesystem.deps import get_filesystem_content_driver, get_filesystem_uploads


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint,prefix,style", [
    ("", "", "auto"), ("http://minio:9000", "umbod/content", "path"),
])
async def test_rest_s3_selection_is_lazy_cached_and_services_remain_per_operation(
    monkeypatch: pytest.MonkeyPatch, endpoint: str, prefix: str, style: str,
) -> None:
    selected: list[ContentConfig] = []
    content = create_content_driver(InMemoryContentConfig(type="inmemory"))

    def fake_content_factory(config: ContentConfig) -> ContentDriver:
        selected.append(config)
        return content

    monkeypatch.setattr(factory_module, "create_content_driver", fake_content_factory)
    settings = AppConfig(filesystem={"content": {
        "type": "s3", "bucket": "umbod-content", "region": "us-east-1",
        "endpoint_url": endpoint, "prefix": prefix, "addressing_style": style,
    }})
    runtime = await prepared_inmemory_runtime()
    try:
        factories = ConnectorApiDependencyFactories.from_settings(settings, runtime, [])
        assert selected == []

        first = await get_filesystem_content_driver(factories)
        second = await get_filesystem_content_driver(factories)

        assert first is second is content
        assert len(selected) == 1
        assert isinstance(selected[0], S3ContentConfig)
        assert selected[0].model_dump() == settings.filesystem.content.model_dump()
        resolver = VerifiedIdentityResolver()
        clock = SystemUploadClock()
        first_uploads = get_filesystem_uploads(runtime.database, resolver, first, 1024, clock)
        second_uploads = get_filesystem_uploads(runtime.database, resolver, second, 1024, clock)
        assert first_uploads is not second_uploads
        assert len(selected) == 1
    finally:
        await runtime.shutdown()
