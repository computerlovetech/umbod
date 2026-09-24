import json
import os
from pathlib import Path
from typing import Any, Protocol

from pydantic import ConfigDict, ValidationError
from umbod.proxies import Model

from umbod.core.connectors.native.models import NonEmptyString


class DeploymentConnectorAvailabilityItem(Model):
    model_config = ConfigDict(extra="forbid")

    id: NonEmptyString


class DeploymentConnectorAvailability(Model):
    model_config = ConfigDict(extra="forbid")

    connectors: list[DeploymentConnectorAvailabilityItem]

    @property
    def connector_ids(self) -> list[str]:
        return [connector.id for connector in self._connector_items()]

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "DeploymentConnectorAvailability":
        return cls.model_validate(payload)

    def _connector_items(self) -> list[DeploymentConnectorAvailabilityItem]:
        return self.connectors


class DeploymentConnectorAvailabilitySource(Protocol):
    def load(self) -> DeploymentConnectorAvailability: ...

    def _availability_contract(self) -> None: ...


class JsonFileDeploymentConnectorAvailabilityDeclaration:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load(self) -> DeploymentConnectorAvailability:
        payload = _connector_availability_payload_from_text(self._payload_text())
        return _availability_from_payload(payload)

    def _payload_text(self) -> str:
        if not self._path.exists():
            raise ValueError(
                f"connector availability declaration file {self._path} could not be found"
            )
        return self._path.read_text(encoding="utf-8")


class JsonFileDeploymentConnectorAvailabilitySource:
    def __init__(self, path: str | Path) -> None:
        self._declaration = JsonFileDeploymentConnectorAvailabilityDeclaration(path)

    def load(self) -> DeploymentConnectorAvailability:
        return self._declaration.load()

    def _availability_contract(self) -> None:
        return None


def _connector_availability_payload_from_text(payload_text: str) -> Any:
    try:
        return json.loads(payload_text)
    except json.JSONDecodeError as error:
        raise ValueError("connector availability declaration is invalid") from error


def _availability_from_payload(payload: Any) -> DeploymentConnectorAvailability:
    try:
        return DeploymentConnectorAvailability.model_validate(payload)
    except ValidationError as error:
        extra_fields = _extra_connector_fields(error)
        if extra_fields:
            fields = ", ".join(extra_fields)
            raise ValueError(_unexpected_fields_message(fields)) from error
        raise ValueError("connector availability declaration is invalid") from error


def _unexpected_fields_message(fields: str) -> str:
    return f"connector availability declaration contains unsupported connector fields; unexpected fields: {fields}"


CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH_VARIABLE = "UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH"


def deployment_connector_availability_source_from_environment(
    variable_name: str,
) -> DeploymentConnectorAvailabilitySource:
    path = os.environ.get(variable_name)
    if path is None or not path.strip():
        raise ValueError(f"{variable_name} is required to declare available connector ids")
    return JsonFileDeploymentConnectorAvailabilitySource(path)


def _extra_connector_fields(error: Any) -> list[str]:
    fields: list[str] = []
    for item in error.errors():
        if item.get("type") != "extra_forbidden":
            continue
        location = item.get("loc", ())
        if len(location) >= 3 and location[0] == "connectors" and isinstance(location[-1], str):
            fields.append(location[-1])
    return fields
