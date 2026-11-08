from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from umbod.core.telemetry.normalization import NormalizationEvidence

from .models import AnalyticsModel, DimensionGroup, NonblankString, UtcDatetime


class UnownedLog(AnalyticsModel):
    kind: Literal["unowned"]


class OwnedLog(AnalyticsModel):
    kind: Literal["owned"]
    owner_id: NonblankString


class AnalyticsLogRecord(AnalyticsModel):
    normalization: NormalizationEvidence
    occurred_at: UtcDatetime
    owner: Annotated[UnownedLog | OwnedLog, Field(discriminator="kind")]
    dimensions: tuple[DimensionGroup, ...]

    @model_validator(mode="after")
    def unique_dimensions(self) -> Self:
        dimensions = tuple(item.dimension for item in self.dimensions)
        if len(set(dimensions)) != len(dimensions):
            raise ValueError("Log dimensions must be unique")
        return self


class LogWriteBatch(AnalyticsModel):
    records: tuple[AnalyticsLogRecord, ...]
