from hashlib import sha256
from json import dumps
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, StrictBytes, model_validator

from umbod.core.telemetry.normalization import NormalizationEvidence

from .models import AnalyticsModel, DimensionGroup, NonblankString, UtcDatetime


class UnownedLog(AnalyticsModel):
    kind: Literal["unowned"]


class OwnedLog(AnalyticsModel):
    kind: Literal["owned"]
    owner_id: NonblankString


LogOwnership = UnownedLog | OwnedLog


def analytics_owner_id(issuer: str, subject: str) -> str:
    identity = dumps((issuer, subject), ensure_ascii=True, separators=(",", ":"))
    return f"oidc:{sha256(identity.encode('ascii')).hexdigest()}"


class AnalyticsLogRecord(AnalyticsModel):
    normalization: NormalizationEvidence
    occurred_at: UtcDatetime
    owner: Annotated[LogOwnership, Field(discriminator="kind")]
    dimensions: tuple[DimensionGroup, ...]

    @model_validator(mode="after")
    def unique_dimensions(self) -> Self:
        dimensions = tuple(item.dimension for item in self.dimensions)
        if len(set(dimensions)) != len(dimensions):
            raise ValueError("Log dimensions must be unique")
        return self


class LogWriteBatch(AnalyticsModel):
    records: tuple[AnalyticsLogRecord, ...]


class LogArchiveSource(AnalyticsModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    raw_payload: Annotated[StrictBytes, Field(min_length=1, repr=False)]
    encoding: Literal["json", "protobuf"]
    received_at: UtcDatetime
    owner: Annotated[LogOwnership, Field(discriminator="kind")]


class ArchivedLogWriteBatch(LogArchiveSource):
    records: Annotated[
        tuple[AnalyticsLogRecord, ...],
        Field(min_length=1, description="Normalized records in original OTLP resource/scope/record order"),
    ]

    @model_validator(mode="after")
    def validate_records(self) -> Self:
        if any(record.owner != self.owner for record in self.records):
            raise ValueError("Archived logs must belong to the trusted owner")
        if any(record.normalization.kind != "normalized" for record in self.records):
            raise ValueError("Archived logs must be normalized")
        return self


LogAppendBatch = LogWriteBatch | ArchivedLogWriteBatch
