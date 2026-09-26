from typing import Annotated

from pydantic import ConfigDict, Field
from umbod_sdk.connectors.plugin_api import ConfigurationCheckResult, Connector
from umbod_sdk.connectors.proxies import Model


class TestConfiguration(Model):
    model_config = ConfigDict(extra="forbid")
    instance_name: str


plugin = Connector(
    id="test",
    name="Kind Runtime Test Connector",
    description="A disposable connector for running-service tests.",
    capability_description="Echo messages in a disposable Kind cluster.",
    configuration=TestConfiguration,
)


@plugin.configuration_check
def check_configuration(configuration: TestConfiguration) -> ConfigurationCheckResult:
    return ConfigurationCheckResult(valid=bool(configuration.instance_name))


@plugin.tool(description="Echo a message in the disposable Kind runtime test.")
def echo(
    message: Annotated[str, Field(description="Message to echo.")],
    configuration: TestConfiguration,
) -> dict[str, str]:
    return {"instance_name": configuration.instance_name, "message": message}
