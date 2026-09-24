from typing import Union

from .models import ConnectorConfigurableState, _StrictModel


class ConfigurationError(_StrictModel):
    code: str
    message: str


class ConfigurationConflict(_StrictModel):
    target: str
    expected_revision: int
    current_revision: int


class ConfigurationSucceeded(_StrictModel):
    state: ConnectorConfigurableState


class ConfigurationRejected(_StrictModel):
    error: ConfigurationError
    conflicts: tuple[ConfigurationConflict, ...] = ()


ConfigurationResult = Union[ConfigurationSucceeded, ConfigurationRejected]
