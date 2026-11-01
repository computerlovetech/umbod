from umbod.core.filesystem.authorization.discovery import FilesystemAuthorizationSnapshot
from umbod.core.filesystem.authorization.ports import FilesystemAuthorizationReader


EMPTY_AUTHORIZATION = FilesystemAuthorizationSnapshot(nodes=(), ownerships=(), grants=())


class FilesystemDiscoveryRuntime:
    def __init__(self, reader: FilesystemAuthorizationReader) -> None:
        self._reader = reader
        self._snapshot = EMPTY_AUTHORIZATION

    async def reconcile(self) -> None:
        try:
            snapshot = await self._reader.read()
        except BaseException:
            self._snapshot = EMPTY_AUTHORIZATION
            raise
        self._snapshot = snapshot

    def capture(self) -> FilesystemAuthorizationSnapshot:
        return self._snapshot
