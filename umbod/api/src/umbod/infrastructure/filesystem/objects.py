import os
import stat
from pathlib import Path
from uuid import UUID

from umbod.core.filesystem import StorageFailure, StorageKey

CHUNK_SIZE = 64 * 1024


def validate_key(key: StorageKey) -> None:
    try:
        if UUID(key).hex != key:
            raise ValueError("Noncanonical content key")
    except (ValueError, AttributeError, TypeError) as error:
        raise StorageFailure("Invalid content key") from error


def prepare_directory(directory: Path) -> Path:
    try:
        if directory.is_symlink():
            raise StorageFailure("Storage directory must not be a symlink")
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not directory.is_dir():
            raise StorageFailure("Storage directory is not a directory")
        return directory.resolve(strict=True)
    except OSError as error:
        raise StorageFailure("Cannot prepare storage directory") from error


def open_regular(path: Path, flags: int) -> int:
    descriptor = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise StorageFailure("Storage object is not a regular file")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def sync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
