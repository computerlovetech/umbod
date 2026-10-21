import asyncio
import json

from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from pydantic import TypeAdapter

from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.connectors.native.tools.runtime_state import ConnectorToolRuntimeState
from umbod.core.activation.events import ConnectorToolChangedStreamEvent
from messaging.models import StreamEvent


class HttpConnectorToolRuntimeStateReader:
    def __init__(self, api_base_url: str) -> None:
        self._api_base_url = api_base_url.rstrip("/")
        self._state_adapter = TypeAdapter(ConnectorToolRuntimeState)

    async def get_runtime_state(self, key: ConnectorToolRef) -> ConnectorToolRuntimeState | None:
        return await asyncio.to_thread(self._get_runtime_state_sync, key)

    def _get_runtime_state_sync(self, key: ConnectorToolRef) -> ConnectorToolRuntimeState | None:
        url = f"{self._api_base_url}/system/connectors/{key.connector_id}/tool/{key.operation_name}"
        try:
            with urlopen(url, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code == 404:
                return None
            raise
        return self._state_adapter.validate_python(
            {
                "key": {
                    "connector_id": payload["connector_id"],
                    "operation_name": payload["operation_name"],
                },
                "status": payload["status"],
            }
        )


class HttpConnectorToolChangeStreamReader:
    def __init__(self, api_base_url: str) -> None:
        self._api_base_url = api_base_url.rstrip("/")
        self._events_adapter = TypeAdapter(list[StreamEvent])

    async def list_after(self, sequence: int, limit: int) -> list[ConnectorToolChangedStreamEvent]:
        return await asyncio.to_thread(self._list_after_sync, sequence, limit)

    def _list_after_sync(self, sequence: int, limit: int) -> list[ConnectorToolChangedStreamEvent]:
        query = urlencode(
            {
                "after_sequence": sequence,
                "limit": limit,
                "event_type": "connector.capability_activation.changed",
            }
        )
        url = f"{self._api_base_url}/system/events?{query}"
        with urlopen(url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return [
            ConnectorToolChangedStreamEvent.from_stream_event(event)
            for event in self._events_adapter.validate_python(payload)
        ]
