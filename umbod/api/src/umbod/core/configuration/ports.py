from typing import Protocol

from umbod.proxies import Model

from umbod.core.configuration.models import EncryptedConnectorConfiguration


class ConnectorCurrentConfigurationStore(Protocol):
    async def get_current_configuration(self, connector_id: str) -> Model | None: ...

    async def save_current_configuration(self, connector_id: str, configuration: Model) -> None: ...

    async def delete_current_configuration(self, connector_id: str) -> None: ...


class ConnectorConfigurationRegistryProtocol(Protocol):
    def get_schema(self, connector_id: str) -> type[Model]: ...


class EncryptedConnectorConfigurationReaderProtocol(Protocol):
    async def get_encrypted_configuration(
        self, connector_id: str
    ) -> EncryptedConnectorConfiguration | None: ...


class EncryptedConnectorConfigurationWriterProtocol(Protocol):
    async def save_encrypted_configuration(
        self, configuration: EncryptedConnectorConfiguration
    ) -> None: ...

    async def delete_encrypted_configuration(self, connector_id: str) -> None: ...


class EncryptedConnectorConfigurationStoreProtocol(
    EncryptedConnectorConfigurationReaderProtocol,
    EncryptedConnectorConfigurationWriterProtocol,
    Protocol,
):
    pass


class EncryptedConnectorConfigurationQueryProtocol(Protocol):
    async def count_configurations_for_connector(self, connector_id: str) -> int: ...


class ConnectorConfigurationSecretProtocol(Protocol):
    def get_secret(self) -> str: ...
