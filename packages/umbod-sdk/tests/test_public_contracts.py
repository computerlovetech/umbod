from importlib import import_module
from importlib.metadata import distribution

import pytest
from pydantic import ConfigDict, Field

from umbod_sdk.connectors import ConfigurationCheckResult, Connector
from umbod_sdk.connectors.discovery import index_connector_plugins
from umbod_sdk.connectors.proxies import Model


class ConnectorConfiguration(Model):
    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(description="Connector endpoint.")


def _connector(connector_id: str = "sample") -> Connector:
    connector = Connector(
        id=connector_id,
        name="Sample",
        description="Sample connector.",
        capability_description="Read sample records.",
        configuration=ConnectorConfiguration,
    )

    @connector.configuration_check
    def check_configuration(configuration: ConnectorConfiguration) -> ConfigurationCheckResult:
        return ConfigurationCheckResult.valid()

    @connector.tool(description="Read a sample record.")
    def read_record(
        record_id: str = Field(description="Record identifier."),
    ) -> dict[str, str]:
        return {"record_id": record_id}

    return connector


def test_plugin_api_is_exposed_from_umbod_sdk_namespace() -> None:
    plugin_api = import_module("umbod_sdk.connectors.plugin_api")

    assert plugin_api.Connector is Connector


def test_distribution_does_not_expose_legacy_connectors_namespace() -> None:
    installed_files = distribution("umbod").files or []

    assert not any(str(installed_file).startswith("connectors/") for installed_file in installed_files)


def test_connector_registration_uses_sdk_owned_contracts() -> None:
    registration = _connector().registration()

    assert registration["capability_description"] == "Read sample records."
    tool_description = registration["tool_descriptions"][0]
    assert tool_description["operation_name"] == "read_record"
    assert tool_description["output_schema_status"] == "absent"


def test_discovery_index_rejects_duplicate_connector_ids() -> None:
    with pytest.raises(ValueError, match="duplicate connector id: sample"):
        index_connector_plugins([_connector(), _connector()])
