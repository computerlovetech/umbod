from collections.abc import Collection, Sequence

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from messaging.ports import EventStream

from umbod.core.activation import ActivationListFilter, ActivationPort
from umbod.core.invocation import (
    ConnectorInvocationPolicyRevisionConflict,
    ConnectorInvocationPolicyStore,
    ConnectorKind,
)
from umbod.core.invocation.tools.configuration import (
    ActivationEventPublicationPolicy,
    NoConnectorToolConfigurationEventStream,
    SetConnectorToolConfiguration,
    SetConnectorToolConfigurationCommand,
)
from umbod.core.invocation.tools.configuration_mutation import (
    ConnectorToolConfigurationMutationPort,
)
from umbod.rest.connectors.invocation_policy import (
    invocation_policy_conflict_response,
    list_invocation_policies,
)
from umbod.rest.connectors.schemas import (
    ToolActivationBatchRequestItem,
    ToolActivationBatchResponse,
    ToolActivationBatchResponseItem,
)


async def list_tool_activations(
    *,
    connector_kind: ConnectorKind,
    connector_id: str,
    activation_port: ActivationPort,
    policy_store: ConnectorInvocationPolicyStore,
    operation_names: Sequence[str] | None = None,
    activation_filter: ActivationListFilter | None = None,
) -> ToolActivationBatchResponse:
    tools = await activation_port.list_activations(
        connector_id,
        "tool",
        activation_filter if activation_filter is not None else ActivationListFilter(),
    )
    names = (
        tuple(operation_names)
        if operation_names is not None
        else tuple(tool.ref.capability_key for tool in tools)
    )
    policies = await list_invocation_policies(connector_kind, connector_id, names, policy_store)
    policy_by_name = {item.tool_id: item for item in policies.tools}
    return ToolActivationBatchResponse(
        connector_id=connector_id,
        tools=[
            ToolActivationBatchResponseItem(
                tool_id=tool.ref.capability_key,
                activation_status=tool.activation_status.value,
                invocation_mode=policy_by_name[tool.ref.capability_key].mode,
                policy_revision=policy_by_name[tool.ref.capability_key].revision,
            )
            for tool in tools
        ],
    )


async def put_tool_activations(
    *,
    connector_kind: ConnectorKind,
    connector_id: str,
    items: Sequence[ToolActivationBatchRequestItem],
    known_operation_names: Collection[str],
    mutation_port: ConnectorToolConfigurationMutationPort,
    event_stream: EventStream | None,
    activation_event_policy: ActivationEventPublicationPolicy,
    unknown_tool_error: HTTPException | None = None,
) -> ToolActivationBatchResponse | JSONResponse:
    if any(item.tool_id not in known_operation_names for item in items):
        if unknown_tool_error is not None:
            raise unknown_tool_error
        raise HTTPException(status_code=404, detail="Connector tool was not found")
    try:
        mutation_result = await SetConnectorToolConfiguration(
            mutation_port,
            event_stream or NoConnectorToolConfigurationEventStream(),
            activation_event_policy,
        ).execute(
            SetConnectorToolConfigurationCommand.model_validate(
                {
                    "connector_kind": connector_kind,
                    "connector_id": connector_id,
                    "items": [
                        {
                            "operation_name": item.tool_id,
                            **item.model_dump(exclude_none=True, exclude={"tool_id"}),
                        }
                        for item in items
                    ],
                }
            )
        )
    except ConnectorInvocationPolicyRevisionConflict as error:
        return invocation_policy_conflict_response(error)
    return ToolActivationBatchResponse(
        connector_id=connector_id,
        tools=[
            ToolActivationBatchResponseItem(
                tool_id=snapshot.operation_name,
                activation_status=snapshot.activation_status.value,
                invocation_mode=snapshot.invocation_mode,
                policy_revision=snapshot.policy_revision,
            )
            for snapshot in mutation_result.snapshots
        ],
    )
