from collections.abc import Callable, Mapping
from typing import Any, cast

from fastmcp.server.auth import AuthContext

from umbod.core.capabilities.domain import CapabilityKind
from umbod.core.permissions import (
    ConnectorCapabilityPermission,
    ConnectorCapabilityRef,
    InMemoryGroupConnectorToolPermissions,
)


def connector_capability_permission_check(
    permissions: InMemoryGroupConnectorToolPermissions,
) -> Callable[[AuthContext], bool]:
    def check(context: AuthContext) -> bool:
        ref = _capability_ref_from_context(context)
        if ref is None:
            return True
        token = context.token
        claims = getattr(token, "claims", {}) if token is not None else {}
        if not isinstance(claims, Mapping):
            return False
        return ConnectorCapabilityPermission(
            connector_id=ref.connector_id,
            capability_kind=ref.capability_kind,
            capability_key=ref.capability_key,
        ) in permissions.allowed_capabilities(claims)

    return check


def connector_tool_permission_check(
    permissions: InMemoryGroupConnectorToolPermissions,
) -> Callable[[AuthContext], bool]:
    return connector_capability_permission_check(permissions)


def _capability_ref_from_context(context: AuthContext) -> ConnectorCapabilityRef | None:
    tool = context.tool
    if tool is not None:
        metadata = tool.get_meta()
        connector_id = metadata.get("connector_id") if isinstance(metadata, Mapping) else None
        operation_name = metadata.get("operation_name") if isinstance(metadata, Mapping) else None
        if isinstance(connector_id, str) and isinstance(operation_name, str):
            return ConnectorCapabilityRef(
                connector_id=connector_id,
                capability_kind="tool",
                capability_key=operation_name,
            )
        return None

    component = getattr(context, "component", None)
    if component is None:
        return None
    metadata = _component_meta(component)
    connector_id = metadata.get("connector_id")
    capability_kind = metadata.get("capability_kind")
    capability_key = metadata.get("capability_key") or metadata.get("operation_name")
    if (
        isinstance(connector_id, str)
        and isinstance(capability_kind, str)
        and isinstance(capability_key, str)
        and capability_kind in {"tool", "prompt", "resource", "resource_template"}
    ):
        return ConnectorCapabilityRef(
            connector_id=connector_id,
            capability_kind=cast(CapabilityKind, capability_kind),
            capability_key=capability_key,
        )
    return None


def _component_meta(component: Any) -> Mapping[str, object]:
    get_meta = getattr(component, "get_meta", None)
    if callable(get_meta):
        metadata = get_meta()
        if isinstance(metadata, Mapping):
            return metadata
    metadata = getattr(component, "meta", None)
    if isinstance(metadata, Mapping):
        return metadata
    return {}
