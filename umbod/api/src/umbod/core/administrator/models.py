from datetime import datetime
from typing import Literal
from typing import Annotated

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from umbod.proxies import Model
from umbod.core.permissions.domain import (
    CapabilityPermissionUpdate,
    ConnectorPermissionUpdate,
)
from umbod.core.publishing import PublishState

from .connector_configuration.models import ConnectorReference


class AdministratorModel(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ConnectorInventoryEntry(AdministratorModel):
    connector: ConnectorReference
    display_name: str
    publication_state: PublishState
    authorization_mode: Literal["shared", "personal"]


class SearchObservedUsers(AdministratorModel):
    query: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    limit: int = Field(default=20, strict=True, ge=1, le=100)


class ObservedUserSummary(AdministratorModel):
    user_id: str
    name: str
    email: str
    last_seen_at: datetime


class ObservedUserMatches(AdministratorModel):
    users: tuple[ObservedUserSummary, ...]
    has_more: bool


class PatchGroupPermissions(AdministratorModel):
    group_id: Annotated[str, StringConstraints(pattern=r"\S")]
    connectors: tuple[ConnectorPermissionUpdate, ...] = ()
    capabilities: tuple[CapabilityPermissionUpdate, ...] = ()

    @model_validator(mode="after")
    def validate_targets(self) -> "PatchGroupPermissions":
        connectors = tuple(item.connector_id for item in self.connectors)
        capabilities = tuple(item.capability for item in self.capabilities)
        if not connectors and not capabilities:
            raise ValueError("At least one permission change is required")
        target_keys = (
            *connectors,
            *(
                key
                for target in capabilities
                for key in (target.connector_id, target.capability_key)
            ),
        )
        if any(not isinstance(key, str) or not key for key in target_keys):
            raise ValueError("Connector IDs and capability keys must not be empty")
        if any(
            item.permission_status not in ("enabled", "disabled")
            for item in (*self.connectors, *self.capabilities)
        ):
            raise ValueError("Permission status must be enabled or disabled")
        if any(
            target.capability_kind
            not in ("tool", "prompt", "resource", "resource_template")
            for target in capabilities
        ):
            raise ValueError("Invalid capability kind")
        if len(connectors) != len(set(connectors)) or len(capabilities) != len(
            set(capabilities)
        ):
            raise ValueError("Duplicate permission target")
        return self
