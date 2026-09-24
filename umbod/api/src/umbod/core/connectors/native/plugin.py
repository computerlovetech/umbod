from collections.abc import Mapping
from typing import Protocol

from umbod_sdk.connectors.api.definition import ConnectorDefinition

ConnectorRegistration = Mapping[str, object]


class ConnectorPlugin(Protocol):
    def definition(self) -> ConnectorDefinition: ...

    def registration(self) -> ConnectorRegistration: ...


__all__ = ["ConnectorPlugin"]
