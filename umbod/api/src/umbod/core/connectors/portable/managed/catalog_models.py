from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Literal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ManagedConnectorSummary:
    connector_id: UUID
    name: str
    description: str
    status: Literal["inactive"]
    configured: bool


@dataclass(frozen=True, slots=True)
class ManagedConfigurationField:
    name: str
    label: str
    required: bool
    min_length: int
    max_length: int
    choices: tuple[str, ...]


class UnsavedConfiguration(Enum):
    NOT_SAVED = auto()


@dataclass(frozen=True, slots=True)
class SavedConfiguration:
    values: dict[str, str] = field(repr=False)


@dataclass(frozen=True, slots=True)
class ManagedConnectorConfiguration:
    connector: ManagedConnectorSummary
    fields: tuple[ManagedConfigurationField, ...]
    configuration: SavedConfiguration | UnsavedConfiguration


class ManagedConfigurationRejected(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ManagedConfigurationFieldRejected(ManagedConfigurationRejected):
    def __init__(self, code: str, field_name: str) -> None:
        super().__init__(code)
        self.field_name = field_name
