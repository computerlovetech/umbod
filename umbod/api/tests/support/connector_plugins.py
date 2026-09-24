from typing import Annotated, Any

from pydantic import ConfigDict, Field, SecretStr
from umbod_sdk.connectors import ConfigurationCheckResult, Connector
from umbod_sdk.connectors.proxies import Model


class SlackAdminConfiguration(Model):
    model_config = ConfigDict(extra='forbid')
    workspace_name: str
    bot_token: SecretStr
    default_channel_id: str


class TestConnectorAdminConfiguration(Model):
    model_config = ConfigDict(extra='forbid')
    instance_name: str
    api_key: SecretStr
    default_response: str


TestConnectorPlugin = Connector(
    id='test',
    name='Test Connector',
    description='Provides a simple connector for validating configuration and MCP publishing flows',
    capability_description='Echo messages and validate connector configuration and publishing flows.',
    configuration=TestConnectorAdminConfiguration,
    extension={'source': 'built-in'},
)


@TestConnectorPlugin.configuration_check
def check_configuration(configuration: TestConnectorAdminConfiguration) -> ConfigurationCheckResult:
    if configuration.api_key.get_secret_value() == 'test-key':
        return ConfigurationCheckResult(valid=True)
    return ConfigurationCheckResult(valid=False, message='Test Connector API key must be "test-key" before publishing.', field_messages={'api_key': 'Use "test-key" for the local Test Connector.'})


@TestConnectorPlugin.tool(description='Return the configured default response for the Test Connector.')
def get_default_response(configuration: TestConnectorAdminConfiguration) -> dict[str, Any]:
    return {'instance_name': configuration.instance_name, 'response': configuration.default_response}


@TestConnectorPlugin.tool(description='Echo a message through the configured Test Connector.')
def echo(message: Annotated[str, Field(description='Message to echo through the Test Connector.')], configuration: TestConnectorAdminConfiguration) -> dict[str, Any]:
    return {'instance_name': configuration.instance_name, 'message': message, 'response': configuration.default_response}


@TestConnectorPlugin.prompt(description='Create a test prompt using the configured Test Connector response.')
def test_prompt(topic: Annotated[str, Field(description='Topic to include in the test prompt.')], configuration: TestConnectorAdminConfiguration) -> str:
    return f'Use {configuration.instance_name} to test {topic}. Default response: {configuration.default_response}'


SlackConnectorPlugin = Connector(id='slack', name='Slack', description='Connects to Slack workspaces and channels', capability_description='Search Slack conversations and read channel messages and threads.', configuration=SlackAdminConfiguration, extension={'source': 'built-in'})


@SlackConnectorPlugin.configuration_check
def check_slack_configuration(configuration: SlackAdminConfiguration) -> ConfigurationCheckResult:
    return ConfigurationCheckResult(valid=True)


@SlackConnectorPlugin.tool(description='List readable Slack channels configured for the Slack connector.')
def list_readable_channels(configuration: SlackAdminConfiguration) -> dict[str, Any]:
    return {'channels': [{'channel_id': configuration.default_channel_id}]}


@SlackConnectorPlugin.tool(description='Read recent messages from a configured Slack channel.')
def read_messages(channel_id: Annotated[str, Field(description='Slack channel ID to read messages from.')], configuration: SlackAdminConfiguration, limit: Annotated[int | None, Field(description='Maximum number of messages to return.')]) -> dict[str, Any]:
    raise RuntimeError('Slack access is unavailable')


@SlackConnectorPlugin.tool(description='Read a Slack message thread from a configured channel.')
def read_thread(channel_id: Annotated[str, Field(description='Slack channel ID containing the thread.')], parent_ts: Annotated[str, Field(description='Slack timestamp of the parent message.')], configuration: SlackAdminConfiguration) -> dict[str, Any]:
    raise RuntimeError('Slack access is unavailable')


@SlackConnectorPlugin.tool(description='Search messages in a configured Slack channel.')
def search_messages(channel_id: Annotated[str, Field(description='Slack channel ID to search in.')], query: Annotated[str, Field(description='Search query text.')], configuration: SlackAdminConfiguration, limit: Annotated[int | None, Field(description='Maximum number of matching messages to return.')]) -> dict[str, Any]:
    raise RuntimeError('Slack access is unavailable')


@TestConnectorPlugin.resource('test://responses/{topic}', name='test_response', description='Read the configured Test Connector response for a topic.')
def test_response(topic: Annotated[str, Field(description='Topic to include in the resource response.')], configuration: TestConnectorAdminConfiguration) -> str:
    return f'{configuration.instance_name} response for {topic}: {configuration.default_response}'
