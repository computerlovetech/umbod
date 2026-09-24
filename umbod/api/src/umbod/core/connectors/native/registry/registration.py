from collections.abc import Sequence

from umbod.core.connectors.native.registry.builder import ConnectorDefinitionBuilder
from umbod.core.connectors.native.registry.domain import ConnectorDefinition, ConnectorRegistration


def connector_definitions_from_registrations(
    registrations: Sequence[ConnectorRegistration],
    available_connector_ids: Sequence[str],
) -> list[ConnectorDefinition]:
    seen_ids: set[str] = set()
    builders = [
        ConnectorDefinitionBuilder(registration, seen_ids) for registration in registrations
    ]
    available_ids = _available_connector_ids_set(
        [builder.connector_id for builder in builders],
        available_connector_ids,
    )
    return [builder.build(builder.connector_id in available_ids) for builder in builders]


def _available_connector_ids_set(
    connector_ids: Sequence[str],
    available_connector_ids: Sequence[str],
) -> set[str]:
    installed_ids = set(connector_ids)
    unknown_connector_ids = [
        connector_id
        for connector_id in available_connector_ids
        if connector_id not in installed_ids
    ]
    if unknown_connector_ids:
        unknown_ids = ", ".join(unknown_connector_ids)
        installed_ids_text = ", ".join(connector_ids)
        raise ValueError(
            f"unknown available connector ids: {unknown_ids}; installed connector ids: {installed_ids_text}"
        )
    return set(available_connector_ids)
