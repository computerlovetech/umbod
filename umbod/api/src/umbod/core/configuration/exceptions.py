class ConnectorConfigurationError(Exception):
    pass


class UnknownConnectorConfigurationError(ConnectorConfigurationError):
    pass


class ConnectorConfigurationValidationError(ConnectorConfigurationError):
    def __init__(self, validation_details: list[dict[str, object]]) -> None:
        super().__init__(str(validation_details))
        self.validation_details = validation_details


class ConnectorConfigurationSecretUnavailableError(ConnectorConfigurationError):
    pass


class ConnectorConfigurationDecryptionError(ConnectorConfigurationError):
    pass


class ConnectorConfigurationNotFoundError(ConnectorConfigurationError):
    pass


class ConnectorConfigurationPermissionError(ConnectorConfigurationError):
    pass
