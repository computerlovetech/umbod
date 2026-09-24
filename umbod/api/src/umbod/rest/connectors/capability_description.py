from umbod.core.capabilities.descriptions import (
    CapabilityDescription,
    ConnectorCapabilityDescriptionKey,
    ConnectorCapabilityDescriptionOverrideStore,
    ConnectorKind,
    OverriddenCapabilityDescription,
)
from umbod.rest.connectors.schemas import CapabilityDescriptionOverrideResponse


async def capability_description_fields(
    *,
    connector_kind: ConnectorKind,
    connector_id: str,
    base_description: CapabilityDescription,
    override_store: ConnectorCapabilityDescriptionOverrideStore,
) -> dict[str, object]:
    state = await override_store.get(
        ConnectorCapabilityDescriptionKey(kind=connector_kind, connector_id=connector_id)
    )
    effective = (
        state.description
        if isinstance(state, OverriddenCapabilityDescription)
        else base_description
    )
    return {
        "capability_description": effective,
        "base_capability_description": base_description,
        "effective_capability_description": effective,
        "capability_description_override": CapabilityDescriptionOverrideResponse(
            state=state.state, revision=state.revision
        ),
    }
