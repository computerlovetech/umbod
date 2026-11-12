from typing import Self

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator


class PersonalUsageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    queue_capacity: int = Field(default=4096, ge=1, le=65536)
    max_record_bytes: int = Field(default=2048, ge=256, le=65536)
    batch_size: int = Field(default=128, ge=1, le=1024)
    flush_interval_seconds: FiniteFloat = Field(default=1.0, gt=0, le=60)
    write_timeout_seconds: FiniteFloat = Field(default=5.0, gt=0, le=60)
    max_retries: int = Field(default=3, ge=0, le=5)
    shutdown_timeout_seconds: FiniteFloat = Field(default=10.0, gt=0, le=120)
    retention_days: int = Field(default=90, ge=1, le=3650)

    @model_validator(mode="after")
    def validate_batch_capacity(self) -> Self:
        if self.batch_size > self.queue_capacity:
            raise ValueError("Personal usage batch size cannot exceed queue capacity")
        return self
