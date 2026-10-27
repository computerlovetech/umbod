from typing import cast

from umbod.core.capabilities.domain import CapabilityKind
from umbod.core.permissions.domain import ConnectorCapabilityRef, GroupPermissionSet, _capability_sort_key
from umbod.core.permissions.stores.schema import (
    CAPABILITY_PERMISSION_GROUP_ID,
    CAPABILITY_PERMISSION_TABLE,
    CONNECTOR_PERMISSION_GROUP_ID,
    CONNECTOR_PERMISSION_TABLE,
    GroupCapabilityPermissionRecord,
    GroupConnectorPermissionRecord,
)
from umbod.core.persistence.plan import ManyRead, ReadPlanOperations
from umbod.core.persistence.query import AllFields, OneOf, Query, Unordered

PERMISSION_READ_BATCH_SIZE = 200


def plan_connector_permission_reads(
    plan: ReadPlanOperations, group_ids: tuple[str, ...]
) -> tuple[ManyRead[GroupConnectorPermissionRecord], ...]:
    identifiers = tuple(sorted(set(group_ids)))
    return tuple(
        plan.find_many(
            CONNECTOR_PERMISSION_TABLE,
            Query(
                filter=OneOf(CONNECTOR_PERMISSION_GROUP_ID, identifiers[start:start + PERMISSION_READ_BATCH_SIZE]),
                projection=AllFields[GroupConnectorPermissionRecord](),
                ordering=Unordered(),
            ),
        )
        for start in range(0, len(identifiers), PERMISSION_READ_BATCH_SIZE)
    )


def plan_capability_permission_reads(
    plan: ReadPlanOperations, group_ids: tuple[str, ...]
) -> tuple[ManyRead[GroupCapabilityPermissionRecord], ...]:
    identifiers = tuple(sorted(set(group_ids)))
    return tuple(
        plan.find_many(
            CAPABILITY_PERMISSION_TABLE,
            Query(
                filter=OneOf(CAPABILITY_PERMISSION_GROUP_ID, identifiers[start:start + PERMISSION_READ_BATCH_SIZE]),
                projection=AllFields[GroupCapabilityPermissionRecord](),
                ordering=Unordered(),
            ),
        )
        for start in range(0, len(identifiers), PERMISSION_READ_BATCH_SIZE)
    )


class PermissionReadState:
    def __init__(
        self,
        connector_rows: tuple[GroupConnectorPermissionRecord, ...],
        capability_rows: tuple[GroupCapabilityPermissionRecord, ...],
    ) -> None:
        connectors: dict[str, set[str]] = {}
        capabilities: dict[str, set[ConnectorCapabilityRef]] = {}
        for connector_row in connector_rows:
            connectors.setdefault(connector_row.group_id, set()).add(connector_row.connector_id)
        for row in capability_rows:
            capabilities.setdefault(row.group_id, set()).add(ConnectorCapabilityRef(
                row.connector_id, _capability_kind(row.capability_kind), row.capability_key,
            ))
        self._permissions = {
            group_id: GroupPermissionSet(
                group_id=group_id,
                connector_ids=tuple(sorted(connectors.get(group_id, ()))),
                capabilities=tuple(sorted(capabilities.get(group_id, ()), key=_capability_sort_key)),
            )
            for group_id in connectors.keys() | capabilities.keys()
        }

    async def list_group_permissions(self, group_id: str) -> GroupPermissionSet:
        return self._permissions.get(group_id, GroupPermissionSet(group_id, (), ()))


def _capability_kind(value: str) -> CapabilityKind:
    if value not in {"tool", "prompt", "resource", "resource_template"}:
        raise ValueError(f"Unsupported capability kind: {value}")
    return cast(CapabilityKind, value)
