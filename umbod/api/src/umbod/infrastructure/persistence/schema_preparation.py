from collections.abc import Sequence

from pydantic import BaseModel

from umbod.core.activation.stores.schema import CAPABILITY_ACTIVATION_STATE_TABLE
from umbod.core.capabilities.descriptions.stores.schema import (
    CAPABILITY_DESCRIPTION_OVERRIDE_TABLE,
)
from umbod.core.configuration.persistence.stores.schema import (
    CONNECTOR_CONFIGURATION_TABLE,
)
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.invocation import APPROVAL_NONCE_TABLE
from umbod.core.invocation import CONNECTOR_INVOCATION_POLICY_TABLE
from umbod.core.connectors.downstream_mcp.stores.schema import (
    CONNECTOR_CREDENTIAL_TABLE,
    CONNECTOR_DEFINITION_TABLE,
    CONNECTOR_HEALTH_TABLE,
    TOOL_CATALOG_TABLE,
)
from umbod.core.connectors.openapi.stores import (
    CATALOG_OPERATION_TABLE,
    CATALOG_SOURCE_TABLE,
    CONNECTOR_TABLE,
    CURRENT_CATALOG_HEADER_TABLE,
)
from umbod.core.permissions.stores.schema import (
    CAPABILITY_PERMISSION_TABLE,
    CONNECTOR_PERMISSION_TABLE,
    GROUP_TABLE,
)
from umbod.core.persistence import Database, Table
from umbod.core.messaging import CHECKPOINT_TABLE, EVENT_TABLE

APPLICATION_PERSISTENCE_TABLES: Sequence[Table[BaseModel, BaseModel]] = (
    CONNECTOR_CONFIGURATION_TABLE,
    PUBLICATION_STATE_TABLE,
    CAPABILITY_ACTIVATION_STATE_TABLE,
    CONNECTOR_INVOCATION_POLICY_TABLE,
    APPROVAL_NONCE_TABLE,
    GROUP_TABLE,
    CONNECTOR_PERMISSION_TABLE,
    CAPABILITY_PERMISSION_TABLE,
    CAPABILITY_DESCRIPTION_OVERRIDE_TABLE,
    CONNECTOR_TABLE,
    CURRENT_CATALOG_HEADER_TABLE,
    CATALOG_SOURCE_TABLE,
    CATALOG_OPERATION_TABLE,
    CONNECTOR_DEFINITION_TABLE,
    CONNECTOR_CREDENTIAL_TABLE,
    TOOL_CATALOG_TABLE,
    CONNECTOR_HEALTH_TABLE,
    EVENT_TABLE,
    CHECKPOINT_TABLE,
)

async def prepare_application_schema(database: Database) -> None:
    await database.ensure_schema(APPLICATION_PERSISTENCE_TABLES)
