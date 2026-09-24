import json
from collections.abc import Mapping
from typing import TypeVar

from pydantic import ValidationError
from umbod.proxies import Model

from umbod.core.configuration.exceptions import (
    ConnectorConfigurationDecryptionError,
    ConnectorConfigurationNotFoundError,
    ConnectorConfigurationPermissionError,
    ConnectorConfigurationValidationError,
)
from umbod.core.configuration.models import (
    ConnectorConfigurationResult,
    EncryptedConnectorConfiguration,
)
from umbod.core.configuration.persistence.crypto import (
    _configuration_plain_json,
    _decrypt,
    _encrypt,
)
from umbod.core.configuration.ports import (
    ConnectorConfigurationRegistryProtocol,
    ConnectorConfigurationSecretProtocol,
    EncryptedConnectorConfigurationStoreProtocol,
)

ConfigurationModel = TypeVar("ConfigurationModel", bound=Model)


class ConnectorConfigurationService:
    def __init__(
        self,
        registry: ConnectorConfigurationRegistryProtocol,
        store: EncryptedConnectorConfigurationStoreProtocol,
        secret: ConnectorConfigurationSecretProtocol,
    ) -> None:
        self.registry = registry
        self.store = store
        self.secret = secret

    async def configure_connector(
        self,
        actor_role: str,
        connector_id: str,
        json_configuration: Mapping[str, object],
    ) -> ConnectorConfigurationResult:
        if actor_role != "administrator":
            raise ConnectorConfigurationPermissionError()
        schema = self.registry.get_schema(connector_id)
        validated = self._validate_configuration(schema, json_configuration)
        await self.save_current_configuration(connector_id, validated)
        return ConnectorConfigurationResult(accepted=True)

    async def get_current_configuration(self, connector_id: str) -> Model | None:
        if await self.store.get_encrypted_configuration(connector_id) is None:
            return None
        schema = self.registry.get_schema(connector_id)
        return await self.get_connector_configuration(connector_id, schema)

    async def save_current_configuration(self, connector_id: str, configuration: Model) -> None:
        secret_value = self.secret.get_secret()
        ciphertext = _encrypt(_configuration_plain_json(configuration), secret_value)
        await self.store.save_encrypted_configuration(
            EncryptedConnectorConfiguration(
                connector_id=connector_id,
                ciphertext=ciphertext,
            )
        )

    async def delete_current_configuration(self, connector_id: str) -> None:
        await self.store.delete_encrypted_configuration(connector_id)

    async def get_connector_configuration(
        self, connector_id: str, schema: type[ConfigurationModel]
    ) -> ConfigurationModel:
        encrypted = await self.store.get_encrypted_configuration(connector_id)
        if encrypted is None:
            raise ConnectorConfigurationNotFoundError(connector_id)
        secret_value = self.secret.get_secret()
        decrypted = _decrypt(encrypted.ciphertext, secret_value)
        try:
            configuration_data = json.loads(decrypted)
        except json.JSONDecodeError as error:
            raise ConnectorConfigurationDecryptionError() from error
        return self._validate_configuration(schema, configuration_data)

    def _validate_configuration(
        self,
        schema: type[ConfigurationModel],
        json_configuration: object,
    ) -> ConfigurationModel:
        try:
            return schema.model_validate(json_configuration)
        except ValidationError as error:
            raise ConnectorConfigurationValidationError(error.errors()) from error
