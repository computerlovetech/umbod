from umbod.core.configuration.exceptions import (
    ConnectorConfigurationSecretUnavailableError,
)
from umbod.core.configuration.ports import ConnectorConfigurationSecretProtocol


class EnvironmentConnectorConfigurationSecret:
    def __init__(self, value: str) -> None:
        if value == "":
            raise ConnectorConfigurationSecretUnavailableError()
        self._value = value

    @classmethod
    def from_value(cls, value: str) -> "EnvironmentConnectorConfigurationSecret":
        return cls(value)

    @classmethod
    def from_environment(cls, variable_name: str) -> "EnvironmentConnectorConfigurationSecret":
        import os

        value = os.getenv(variable_name)
        if value is None:
            raise ConnectorConfigurationSecretUnavailableError()
        return cls(value)

    def get_secret(self) -> str:
        return self._value


class UnavailableConnectorConfigurationSecret:
    def get_secret(self) -> str:
        raise ConnectorConfigurationSecretUnavailableError()


__all__ = [
    "ConnectorConfigurationSecretProtocol",
    "EnvironmentConnectorConfigurationSecret",
    "UnavailableConnectorConfigurationSecret",
]
