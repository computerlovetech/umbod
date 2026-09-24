from collections.abc import Callable, Mapping
from typing import Any, Protocol

from umbod_sdk.connectors.api.definition import ConnectorDefinition

ConnectorRegistration = Mapping[str, object]
ConnectorToolResult = Any
ConnectorToolOperation = Callable[..., ConnectorToolResult]


class ConnectorPlugin(Protocol):
    def definition(self) -> ConnectorDefinition: ...

    def registration(self) -> ConnectorRegistration: ...
