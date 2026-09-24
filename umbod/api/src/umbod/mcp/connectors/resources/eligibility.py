from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import ValidationError

from umbod.core.activation import ActivationStatus, ActivationStore, CapabilityRef
from umbod.core.configuration import ConnectorCurrentConfigurationStore
from umbod.core.publishing import ConnectorPublishingStore
from umbod.proxies import Model


@dataclass(frozen=True)
class ConnectorResourceEligibilityContext:
    schemas: Mapping[str, type[Model]]
    connector_configuration_store: ConnectorCurrentConfigurationStore
    connector_publishing_store: ConnectorPublishingStore
    activation_store: ActivationStore


async def is_connector_resource_eligible(
    *,
    connector_id: str,
    uri_template: str,
    context: ConnectorResourceEligibilityContext,
) -> bool:
    schema = context.schemas.get(connector_id)
    if schema is None:
        return False
    if not await context.connector_publishing_store.is_published(connector_id):
        return False
    configuration = await context.connector_configuration_store.get_current_configuration(
        connector_id
    )
    if configuration is None:
        return False
    try:
        schema.model_validate(configuration.model_dump())
    except ValidationError:
        return False
    status = await context.activation_store.get_status(
        CapabilityRef(
            connector_kind="native",
            connector_id=connector_id,
            capability_kind="resource_template",
            capability_key=uri_template,
        )
    )
    return status == ActivationStatus.ENABLED
