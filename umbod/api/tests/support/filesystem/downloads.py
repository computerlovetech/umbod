from umbod.core.filesystem import ByteStream, ContentRef, StorageFailure, StorageKey
from umbod.core.filesystem.content import ExternalDownloadInstructions, ExternalDownloadRequest
from umbod.infrastructure import InMemoryContentConfig, create_content_driver


class DirectDownloadContent:
    def __init__(self) -> None:
        self._storage = create_content_driver(InMemoryContentConfig(type="inmemory"))
        self.download_requests: list[ExternalDownloadRequest] = []
        self.read_keys: list[StorageKey] = []
        self.fail_signing = False

    async def put(self, data: ByteStream) -> ContentRef:
        return await self._storage.put(data)

    async def prepare_download(self, request: ExternalDownloadRequest) -> ExternalDownloadInstructions:
        self.download_requests.append(request)
        if self.fail_signing:
            raise StorageFailure("private signing diagnostic")
        return ExternalDownloadInstructions(url="https://storage.example.test/object?signature=secret")

    def get(self, key: StorageKey) -> ByteStream:
        self.read_keys.append(key)
        return self._storage.get(key)
