from typing import Annotated

from pydantic import Field, StringConstraints
from umbod_sdk.connectors.proxies import Model

NonEmptyString = Annotated[str, StringConstraints(min_length=1)]


class ConnectorConfigurationCheckResult(Model):
    valid: bool
    message: NonEmptyString | None = None
    field_messages: dict[NonEmptyString, NonEmptyString] = Field(default_factory=dict)
