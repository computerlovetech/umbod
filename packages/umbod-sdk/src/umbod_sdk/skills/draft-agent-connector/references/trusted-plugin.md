# Trusted Pydantic plugins

Use this format for an installed Python plugin that owns its HTTP client. For a single-file connector with explicit schemas, use the [portable connector reference](portable-connector.md) instead.

The connector interface comes from `umbod_sdk.connectors.plugin_api` and `umbod_sdk.connectors.proxies`. Organize the plugin as one Python package with the four files below. Use the `rejseplanen` plugin as an existing reference when it is available in the checkout.

## Plan the plugin

Confirm the base URL, authentication type, and the selected endpoints' request and response shapes against an authoritative source such as OpenAPI. List any contract gaps instead of inventing fields. Keep the tool set focused and choose a read-only endpoint for the configuration check. When providing an icon, use an SVG file referenced by its `.svg` path. Leave entry points, packaging, installation, and deployment to the SDK's connector distribution guide.

## Public interface

```python
from umbod_sdk.connectors.plugin_api import Connector, ConfigurationCheckResult
from umbod_sdk.connectors.proxies import Model  # Pydantic BaseModel proxy — base for config models
```

- `Connector(*, id, name, description, capability_description, configuration)` — declares the connector. `configuration` is your config `Model` subclass.
- `@connector.configuration_check` — decorates a function `(configuration) -> ConfigurationCheckResult` run before publish.
- `@connector.tool(description=...)` — decorates a function that becomes an MCP tool.
- `ConfigurationCheckResult.valid()` / `ConfigurationCheckResult.invalid(message=..., field_messages={...})` — check results. `field_messages` maps a config field name to an error shown on that field in the UI.

## The four files

### `admin_configuration.py` — UI config
A `Model` subclass. Secrets are `SecretStr`. `extra="forbid"`.

```python
from pydantic import ConfigDict, Field, SecretStr
from umbod_sdk.connectors.proxies import Model

class MyAdminConfiguration(Model):
    model_config = ConfigDict(extra="forbid")
    access_id: SecretStr = Field(description="API access key.")
```

### `api_client.py` — HTTP + errors
A settings `Model` (`frozen=True`) holding the base URL, timeout, and secret, plus a client class that builds requests and raises typed errors. Read secrets with `.get_secret_value()`.

```python
class MyApiRequestError(RuntimeError): ...      # request rejected (e.g. bad key)
class MyAccessUnavailableError(RuntimeError): ... # could not reach the API

class MyApiSettings(Model):
    model_config = ConfigDict(frozen=True)
    access_id: SecretStr
    api_base_url: str = "https://api.example.com"
    timeout_seconds: float = 10.0
```

### `configuration_check.py` — live check
Calls the safe live-check endpoint. Return `ConfigurationCheckResult.valid()` on success and `ConfigurationCheckResult.invalid(...)` on failure. Include a `field_messages` entry when an individual configuration field is invalid. Distinguish "rejected" (bad credential) from "unreachable" (upstream down).

### `__init__.py` — assembly

```python
connector = Connector(
    id="myservice",
    name="My Service",
    description="What agents can do with this service.",
    capability_description="Search records in My Service.",
    configuration=MyAdminConfiguration,
)

@connector.configuration_check
def check_configuration(configuration: MyAdminConfiguration) -> ConfigurationCheckResult:
    ...

@connector.tool(description="Plain-language description of what this tool does.")
def search_things(
    query: Annotated[str, Field(description="Search text.")],
    configuration: MyAdminConfiguration,               # <-- INJECTED by Umbod, not a caller arg
    limit: Annotated[int | None, Field(description="Max results.")] = None,
) -> dict[str, Any]:
    return _client(configuration).search(query=query, limit=limit)
```

## Injected `configuration` — the one non-obvious rule

When a tool or configuration check needs settings, declare a parameter named `configuration` and annotate it with the config `Model`. Umbod injects the saved, decrypted configuration by parameter name, not by annotation or position. The agent user never passes it, and tools that do not need settings can omit it. Use `Annotated[..., Field(description=...)]` for public tool inputs so their descriptions reach the MCP schema.

## Tools return raw JSON

Default to returning the API's JSON payload unchanged (`dict[str, Any]`). Only normalize if the user explicitly asked for it.

## Tests (mocked)

Two test modules, mirroring `tests/connectors/plugins/rejseplanen/`:
- `test_*_api_client.py` — mock the HTTP client; assert request params and that responses pass through unchanged.
- `test_*_configuration_check.py` — assert valid path returns `valid=True`, and rejected/unreachable paths return `valid=False` with the right `field_messages`.

No test performs a real network call or uses a real credential.
