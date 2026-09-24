from pydantic import Field
from umbod.rest.proxies import Model

from messaging.models import MessagingEventType


class HealthResponse(Model):
    """Health check result for the Umbod API."""

    status: str = Field(description="Health status of the API service.")
    service: str = Field(description="Name of the service reporting its health.")


class ConnectorRuntimeStateResponse(Model):
    """Runtime availability, publication status, and configuration for a connector."""

    connector_id: str = Field(description="Stable identifier of the connector.")
    display_name: str | None = Field(
        default=None,
        description="Human-readable connector name from connector metadata.",
    )
    available: bool = Field(
        description="Whether the connector is enabled for this deployment.",
    )
    published: bool = Field(
        description="Whether the connector is published and exposed to MCP clients.",
    )
    configuration: dict[str, object] | None = Field(
        description="Current connector configuration values, or null when not configured.",
    )


class ConnectorToolRuntimeStateResponse(Model):
    connector_id: str = Field(description="Stable identifier of the connector.")
    operation_name: str = Field(description="Stable operation name of the connector tool.")
    status: str = Field(description="Current connector tool activation status.")


class EventListQuery(Model):
    """Query parameters for listing system events from the event stream."""

    after_sequence: int = Field(
        default=0,
        ge=0,
        description="Return events with a sequence number greater than this value.",
    )
    limit: int = Field(
        default=100,
        ge=0,
        description="Maximum number of events to return.",
    )
    event_type: list[MessagingEventType] | None = Field(
        default=None,
        description="Filter results to these event types; omit to return all event types.",
    )
