from collections.abc import Iterator
from contextlib import contextmanager
from typing import assert_never

from umbod.core.administrator import (
    AdministratorAccessDenied,
    AdministratorChanges,
    AdministratorDiscovery,
    AdministratorInspection,
)
from umbod.core.administrator.connector_configuration import (
    AdministratorPrincipal,
    ConfigurationRejected,
    ConfigurationResult,
    ConnectorConfigurableState,
)
from umbod.core.filesystem.errors import (
    PolicyConflict,
    PolicyRevisionConflict,
    PolicyUnavailable,
)
from umbod.core.filesystem.namespaces.errors import (
    NamespaceNotFound,
    NamespaceValidationError,
)
from umbod.core.responses import RetryAdvice, ToolErrorDetails
from umbod.mcp.responses.progress import (
    operation_completed,
    operation_rejected_before_work,
    operation_started,
)
from umbod.mcp.tools.errors import BuiltinToolAuthorizationDenied, BuiltinToolRejected

from . import operation_inputs as inputs
from . import operation_results as results
from .connector_configuration.errors import configuration_rejection_error
from .principal import current_administrator_principal


def _configuration(result: ConfigurationResult) -> ConnectorConfigurableState:
    if isinstance(result, ConfigurationRejected):
        rejection = configuration_rejection_error(result)
        issues = tuple(
            issue.model_copy(
                update={
                    "field": "request.connector.connector_id"
                    if issue.field == "connector_id"
                    else f"request.{issue.field}",
                }
            )
            for issue in rejection.details.issues
        )
        raise BuiltinToolRejected(
            rejection.details.message,
            details=rejection.details.model_copy(update={"issues": issues}),
            retry=rejection.retry,
        )
    return result.state


def _rejected(code: str, message: str, retry: RetryAdvice) -> BuiltinToolRejected:
    return BuiltinToolRejected(
        message,
        details=ToolErrorDetails(code=code, message=message, issues=()),
        retry=retry,
    )


class AdministratorOperationFacade:
    def __init__(
        self,
        discovery: AdministratorDiscovery,
        inspection: AdministratorInspection,
        changes: AdministratorChanges,
        membership_claim: str,
    ) -> None:
        self._discovery = discovery
        self._inspection = inspection
        self._changes = changes
        self._membership_claim = membership_claim

    @contextmanager
    def _operation(self) -> Iterator[AdministratorPrincipal]:
        principal = current_administrator_principal(self._membership_claim)
        operation_started()
        try:
            yield principal
        except AdministratorAccessDenied:
            operation_rejected_before_work()
            message = "Administrator membership is required."
            raise BuiltinToolAuthorizationDenied(
                message,
                details=ToolErrorDetails(
                    code="administrator_access_denied", message=message, issues=()
                ),
            ) from None
        except PolicyRevisionConflict:
            raise _rejected(
                "namespace_revision_conflict",
                "The namespace changed. List namespaces again and reconcile the latest revisions before updating.",
                RetryAdvice.AFTER_CORRECTION,
            ) from None
        except NamespaceNotFound:
            raise _rejected(
                "namespace_not_found",
                "The shared namespace was not found. List namespaces again.",
                RetryAdvice.AFTER_CORRECTION,
            ) from None
        except NamespaceValidationError:
            raise _rejected(
                "namespace_invalid",
                "Check the namespace name and registered group assignments.",
                RetryAdvice.AFTER_CORRECTION,
            ) from None
        except PolicyConflict:
            raise _rejected(
                "namespace_conflict",
                "The namespace change conflicts with existing state. List namespaces before trying again.",
                RetryAdvice.AFTER_CORRECTION,
            ) from None
        except PolicyUnavailable:
            raise _rejected(
                "namespace_unavailable",
                "Shared namespace policy is unavailable.",
                RetryAdvice.INSPECT_BEFORE_RETRY,
            ) from None

    async def admin_discover(
        self, request: inputs.DiscoverOperation
    ) -> results.DiscoverResult:
        with self._operation() as principal:
            match request:
                case inputs.ListConnectors():
                    payload = await self._discovery.list_connectors(principal)
                    operation_completed()
                    return results.ConnectorList(
                        operation=request.operation, result=payload
                    )
                case inputs.ListGroups():
                    groups = await self._discovery.list_groups(principal)
                    operation_completed()
                    return results.GroupList(operation=request.operation, result=groups)
                case inputs.ListPermissionTargets():
                    targets = await self._discovery.list_permission_targets(principal)
                    operation_completed()
                    return results.PermissionTargets(
                        operation=request.operation, result=targets
                    )
                case inputs.SearchUsers():
                    users = await self._discovery.search_users(principal, request)
                    operation_completed()
                    return results.UserMatches(
                        operation=request.operation, result=users
                    )
                case inputs.ListNamespaces():
                    namespaces = await self._discovery.list_namespaces(principal)
                    operation_completed()
                    return results.NamespaceList(
                        operation=request.operation, result=namespaces
                    )
            assert_never(request)

    async def admin_inspect(
        self, request: inputs.InspectOperation
    ) -> results.InspectResult:
        with self._operation() as principal:
            match request:
                case inputs.ReadConnector():
                    state = _configuration(
                        await self._inspection.read_connector_configuration(
                            principal, request.connector
                        )
                    )
                    operation_completed()
                    return results.ConnectorConfiguration(
                        operation=request.operation, result=state
                    )
                case inputs.ReadGroupPermissions():
                    grants = await self._inspection.read_group_permissions(
                        principal, request.group_id
                    )
                    operation_completed()
                    return results.GroupPermissions(
                        operation=request.operation, result=grants
                    )
            assert_never(request)

    async def admin_apply(self, request: inputs.ApplyOperation) -> results.ApplyResult:
        with self._operation() as principal:
            match request:
                case inputs.UpdateConnector():
                    state = _configuration(
                        await self._changes.update_connector_configuration(
                            principal, request.connector, request.desired_state
                        )
                    )
                    operation_completed()
                    return results.ConnectorUpdated(
                        operation=request.operation, result=state
                    )
                case inputs.UpdateGroupPermissions():
                    change = await self._changes.update_group_permissions(
                        principal, request
                    )
                    if change.status == "rejected":
                        raise _rejected(
                            "group_permission_update_rejected",
                            "The group permission patch was rejected. Check assignable targets and the exact grant keys.",
                            RetryAdvice.AFTER_CORRECTION,
                        )
                    operation_completed()
                    return results.PermissionsUpdated(
                        operation=request.operation,
                        result=results.AppliedGroupPermissions(
                            group_id=change.group_id
                        ),
                    )
                case inputs.CreateNamespace():
                    namespace = await self._changes.create_namespace(
                        principal, request.namespace
                    )
                    operation_completed()
                    return results.NamespaceCreated(
                        operation=request.operation, result=namespace
                    )
                case inputs.UpdateNamespace():
                    namespace = await self._changes.update_namespace(
                        principal, request.namespace_id, request.namespace
                    )
                    operation_completed()
                    return results.NamespaceUpdated(
                        operation=request.operation, result=namespace
                    )
            assert_never(request)
