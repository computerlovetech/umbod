from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from ..drafts import DraftReceipt


@dataclass(frozen=True, slots=True)
class ManagedConnectorReceipt:
    connector_id: UUID
    revision_id: UUID
    status: Literal["inactive"]


@dataclass(frozen=True, slots=True)
class InactiveConnectorSnapshot:
    declared_connector_id: str
    display_name: str
    description: str
    configuration_schema_json: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class PortableConnectorSubmission:
    revision: DraftReceipt = field(repr=False)
    profile_id: str
    snapshot: InactiveConnectorSnapshot = field(repr=False)
