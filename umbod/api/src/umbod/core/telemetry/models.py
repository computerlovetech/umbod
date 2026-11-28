from enum import Enum

from pydantic import ConfigDict, Field, JsonValue

from umbod.proxies import Model


class TelemetrySignal(str, Enum):
    LOGS = "logs"
    METRICS = "metrics"
    TRACES = "traces"


class TelemetryExport(Model):
    model_config = ConfigDict(frozen=True)

    signal: TelemetrySignal
    payload: dict[str, JsonValue]
    item_count: int = Field(ge=0)
