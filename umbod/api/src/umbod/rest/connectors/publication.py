from typing import Literal, TypeVar

from umbod.core.publishing import ConnectorPublishingStore
from umbod.rest.connectors.schemas import ConnectorPublicationStatus

ConfigureAction = TypeVar("ConfigureAction", bound=str)

NativeAvailableAction = Literal["configure", "publish", "unpublish"]
OpenApiAvailableAction = Literal["import", "publish", "unpublish"]


async def resolve_publication_status(
    *,
    connector_id: str,
    publishing_store: ConnectorPublishingStore,
    is_configured: bool,
) -> ConnectorPublicationStatus:
    if await publishing_store.is_published(connector_id):
        return "published"
    if await publishing_store.was_previously_published(connector_id):
        return "unpublished"
    if is_configured:
        return "draft"
    return "unconfigured"


def available_actions_for_status(
    status: ConnectorPublicationStatus,
    *,
    configure_action: ConfigureAction,
) -> tuple[ConfigureAction | Literal["publish", "unpublish"], ...]:
    if status == "published":
        return (configure_action, "unpublish")
    if status in {"draft", "unpublished"}:
        return (configure_action, "publish")
    return (configure_action,)


def native_available_actions(status: ConnectorPublicationStatus) -> list[NativeAvailableAction]:
    return list(available_actions_for_status(status, configure_action="configure"))


def openapi_available_actions(status: ConnectorPublicationStatus) -> tuple[OpenApiAvailableAction, ...]:
    return available_actions_for_status(status, configure_action="import")
