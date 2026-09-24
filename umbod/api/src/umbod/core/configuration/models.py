from typing import Literal

from umbod.proxies import Model


class EncryptedConnectorConfiguration(Model):
    connector_id: str
    ciphertext: str


class ConnectorConfigurationResult(Model):
    accepted: bool


class ConnectorConfigurationField(Model):
    name: str
    type: Literal["string"]
    required: bool
    secret: bool
