from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ConnectorToolRef:
    connector_id: str
    operation_name: str


ConnectorToolStatus = Literal["enabled", "disabled"]
