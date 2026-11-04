import stat
from pathlib import Path
from typing import cast

from botocore.exceptions import ClientError

from umbod.core.filesystem import StorageFailure, StorageKey

from ..config import S3ContentConfig
from ..keys import validate_key
from ..local_content import LocalContent
from ..s3.edge import ClientProvider
from ..s3.lifecycle import client_scope, finish
from ..s3_content import S3Content
from .ports import MigrationKeys, MigrationStream


def validate_directory(directory: Path) -> None:
    try:
        if not stat.S_ISDIR(directory.lstat().st_mode):
            raise StorageFailure("Migration source must be an existing real directory")
    except OSError:
        raise StorageFailure("Cannot inspect migration source directory") from None


class LocalMigrationSource:
    def __init__(self, directory: Path) -> None:
        validate_directory(directory)
        self._directory = directory

    async def list_keys(self) -> MigrationKeys:
        validate_directory(self._directory)
        try:
            keys: list[StorageKey] = []
            for entry in self._directory.iterdir():
                if not stat.S_ISREG(entry.lstat().st_mode):
                    raise StorageFailure("Migration source contains a nonregular entry")
                if entry.name.startswith(".content-"):
                    continue
                validate_key(entry.name)
                keys.append(entry.name)
            return MigrationKeys(keys=tuple(sorted(keys)))
        except OSError:
            raise StorageFailure("Cannot inspect migration source entries") from None

    def get(self, key: StorageKey) -> MigrationStream:
        validate_directory(self._directory)
        return cast(MigrationStream, LocalContent(self._directory).get(key))


class S3MigrationTarget:
    def __init__(self, config: S3ContentConfig, provider: ClientProvider) -> None:
        self._config = config
        self._provider = provider
        self._content = S3Content(config, provider)

    async def exists(self, key: StorageKey) -> bool:
        validate_key(key)
        object_key = f"{self._config.prefix}/{key}" if self._config.prefix else key
        try:
            async with client_scope(self._provider) as client:
                await finish(client.head_object(Bucket=self._config.bucket, Key=object_key))
            return True
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
                return False
            raise StorageFailure("Cannot inspect migration destination") from None
        except Exception:
            raise StorageFailure("Cannot inspect migration destination") from None

    def get(self, key: StorageKey) -> MigrationStream:
        return cast(MigrationStream, self._content.get(key))

    async def write_at(self, key: StorageKey, stream: MigrationStream) -> None:
        await self._content.put_at(key, stream)
