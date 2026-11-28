from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field

from umbod.proxies import Model


class DeleteFileCommand(Model):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    node_id: UUID
    expected_revision: int = Field(
        ge=1, le=9_999_999_999_999_999_999,
        description="Current file revision from filesystem browsing; deletion fails if it has changed.",
    )


class FileDeletionConfirmation(Model):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    value: bool = Field(title="Confirm file deletion")


class FileDeletionResult(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: UUID
    deleted: Literal[True]
