from fastapi.responses import JSONResponse

from umbod.core.invocation import (
    ConnectorInvocationPolicyKey,
    ConnectorInvocationPolicyRevisionConflict,
    ConnectorInvocationPolicyStore,
    ConnectorKind,
)
from umbod.rest.connectors.schemas import (
    ConnectorToolInvocationPolicyItemResponse,
    ConnectorToolInvocationPolicyListResponse,
)


async def list_invocation_policies(
    connector_kind: ConnectorKind,
    connector_id: str,
    operation_names: tuple[str, ...],
    store: ConnectorInvocationPolicyStore,
) -> ConnectorToolInvocationPolicyListResponse:
    keys = tuple(
        ConnectorInvocationPolicyKey(
            connector_kind=connector_kind,
            connector_id=connector_id,
            operation_name=operation_name,
        )
        for operation_name in operation_names
    )
    records = await store.list(keys)
    return ConnectorToolInvocationPolicyListResponse(
        connector_kind=connector_kind,
        connector_id=connector_id,
        tools=[
            ConnectorToolInvocationPolicyItemResponse(
                tool_id=key.operation_name,
                mode="direct" if record is None else record.mode,
                revision=0 if record is None else record.revision,
            )
            for key, record in zip(keys, records, strict=True)
        ],
    )


def invocation_policy_conflict_response(
    error: ConnectorInvocationPolicyRevisionConflict,
) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "code": "invocation_policy_revision_conflict",
            "conflicts": [
                {
                    "tool_id": conflict.key.operation_name,
                    "expected_revision": conflict.expected_revision,
                    "current_mode": conflict.current_mode,
                    "current_revision": conflict.current_revision,
                }
                for conflict in error.conflicts
            ],
        },
    )
