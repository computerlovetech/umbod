from pathlib import Path

from cryptography.fernet import Fernet
from key_value.aio.protocols import AsyncKeyValue
from key_value.aio.stores.filetree import (
    FileTreeStore,
    FileTreeV1CollectionSanitizationStrategy,
    FileTreeV1KeySanitizationStrategy,
)
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

from umbod.mcp.settings import OIDCOAuthStorageSettings


class MCPOAuthClientStorageFactory:
    def create(self, settings: OIDCOAuthStorageSettings) -> AsyncKeyValue:
        storage_dir = Path(settings.directory)
        storage_dir.mkdir(parents=True, exist_ok=True)
        file_store = FileTreeStore(
            data_directory=storage_dir,
            key_sanitization_strategy=FileTreeV1KeySanitizationStrategy(storage_dir),
            collection_sanitization_strategy=FileTreeV1CollectionSanitizationStrategy(storage_dir),
        )
        return FernetEncryptionWrapper(
            key_value=file_store,
            fernet=Fernet(settings.encryption_key.encode()),
            raise_on_decryption_error=False,
        )
