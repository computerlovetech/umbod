from uuid import UUID

from umbod.core.filesystem import StorageFailure, StorageKey


def validate_key(key: StorageKey) -> None:
    try:
        if UUID(key).hex != key:
            raise ValueError("Noncanonical content key")
    except (ValueError, AttributeError, TypeError):
        raise StorageFailure("Invalid content key") from None
