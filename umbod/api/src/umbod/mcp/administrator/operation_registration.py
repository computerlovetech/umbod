from umbod.mcp.tools import McpObservedToolRegistrar

from .authorization import administrator_authorization_check
from .operation_facade import AdministratorOperationFacade


def register_administrator_operation_tools(
    registrar: McpObservedToolRegistrar,
    facade: AdministratorOperationFacade,
    membership_claim: str,
    required_membership: str,
) -> None:
    authorization = administrator_authorization_check(membership_claim, required_membership)
    registrar.register(
        facade.admin_discover,
        name="admin_discover",
        description=(
            "Discover administration targets. Set request.operation to list_connectors, list_groups, "
            "list_permission_targets, search_users, or list_namespaces. Search users by a nonblank "
            "name or email query; only users observed by Umbod are included. Use exact IDs from results. "
            "List namespaces returns shared namespace policies and current revisions."
        ),
        auth=authorization,
        builtin_response=True,
    )
    registrar.register(
        facade.admin_inspect,
        name="admin_inspect",
        description=(
            "Inspect one administration target. Set request.operation to read_connector_configuration "
            "with a connector kind and ID, or read_group_permissions with an exact group ID. "
            "Connector configuration includes capability keys and revisions. Group permissions are "
            "direct stored grants, including stale grants, not effective access."
        ),
        auth=authorization,
        builtin_response=True,
    )
    registrar.register(
        facade.admin_apply,
        name="admin_apply",
        description=(
            "Apply one administration change. Set request.operation to update_connector_configuration, "
            "update_group_permissions, create_namespace, or update_namespace. Connector and group changes "
            "are patches; omitted targets stay unchanged. Connector activation and policy changes may "
            "target the same tool, but do not repeat targets within an operation type, send multiple "
            "description operations, or repeat group IDs or capability targets within a group. Empty "
            "connector operations only read; a group patch needs at least one change. Enabled adds a "
            "grant; disabled removes it (not a deny). Read connector revisions before changing "
            "invocation policies (tools only) or descriptions. Namespace updates "
            "replace the full group list and require expected_revision. To change a namespace description, "
            "also send expected_root_revision; omit both description fields to preserve it, or send an empty "
            "description to clear it. If the outcome is uncertain, inspect current state before retrying."
        ),
        auth=authorization,
        builtin_response=True,
    )
