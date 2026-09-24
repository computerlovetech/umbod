from typing import Annotated, Literal

from pydantic import ConfigDict, Field, StringConstraints
from umbod.core.capabilities.descriptions.domain import CapabilityDescription
from umbod.core.configuration.models import ConnectorConfigurationField
from umbod.proxies import Model

NonEmptyString = Annotated[str, StringConstraints(min_length=1)]


class ConnectorExtension(Model):
    model_config = ConfigDict(extra="ignore")

    source: Literal["built-in", "user-supplied"]
    package: str | None = None


class ConnectorMetadata(Model):
    model_config = ConfigDict(extra="ignore")

    id: NonEmptyString
    display_name: NonEmptyString
    description: NonEmptyString
    capability_description: CapabilityDescription
    icon_data_url: str | None = Field(default=None, exclude_if=lambda value: value is None)
    extension: ConnectorExtension


class ConnectorConfigurationCheckResult(Model):
    valid: bool
    message: NonEmptyString | None = None
    field_messages: dict[NonEmptyString, NonEmptyString] = Field(default_factory=dict)


__all__ = [
    "ConnectorConfigurationCheckResult",
    "ConnectorConfigurationField",
    "ConnectorExtension",
    "ConnectorMetadata",
    "NonEmptyString",
]
