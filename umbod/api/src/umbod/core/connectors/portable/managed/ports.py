from enum import Enum, auto
from typing import Protocol
from uuid import UUID

from .catalog_models import ManagedConnectorConfiguration, ManagedConnectorSummary, SavedConfiguration

from ..drafts import DraftReceipt
from .models import ManagedConnectorReceipt, PortableConnectorSubmission


class ManagedSubmissionMissing(Enum):
    NOT_SUBMITTED = auto()


class ManagedSubmissionConflict(Exception):
    pass


class ManagedSubmissionLookupUnavailable(Exception):
    pass


class ManagedSubmissionWriteUnconfirmed(Exception):
    pass


class ManagedConnectorNotFound(Exception):
    pass


class ManagedCatalogUnavailable(Exception):
    pass


class ManagedConfigurationWriteUnconfirmed(Exception):
    pass


class ManagedConnectorCatalogStore(Protocol):
    async def list_connectors(self) -> tuple[ManagedConnectorSummary, ...]: ...

    async def read_configuration(self, connector_id: UUID) -> ManagedConnectorConfiguration: ...

    async def replace_configuration(self, connector_id: UUID, configuration: SavedConfiguration) -> None: ...


class ManagedConnectorStore(Protocol):
    async def find_submission(self, revision: DraftReceipt) -> ManagedConnectorReceipt | ManagedSubmissionMissing: ...

    async def submit(self, submission: PortableConnectorSubmission) -> ManagedConnectorReceipt: ...
