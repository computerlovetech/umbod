from dataclasses import dataclass

from umbod.core.capabilities.tools.refs import (
    ConnectorToolRef,
    ConnectorToolStatus,
)


@dataclass(frozen=True)
class ConnectorToolRuntimeState:
    key: ConnectorToolRef
    status: ConnectorToolStatus
