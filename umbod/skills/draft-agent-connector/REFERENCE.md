# Connector Interface Reference

Everything a connector needs comes from `umbod_sdk.connectors.plugin_api` and `umbod_sdk.connectors.proxies`. A connector is one Python package with four files. Use the `rejseplanen` plugin as the canonical example.

## Public interface

```python
from umbod_sdk.connectors.plugin_api import Connector, ConfigurationCheckResult
from umbod_sdk.connectors.proxies import Model  # Pydantic BaseModel proxy — base for config models
```

- `Connector(*, id, name, description, configuration)` — declares the connector. `configuration` is your config `Model` subclass.
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
Calls the safe live-check endpoint. Returns `ConnectorConfigurationCheckResult(valid=True)` on success, or `valid=False` with a `field_messages` entry naming the offending config field on failure. Distinguish "rejected" (bad credential) from "unreachable" (upstream down).

### `__init__.py` — assembly

```python
connector = Connector(
    id="myservice",
    name="My Service",
    description="What agents can do with this service.",
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

Every tool and the config-check function declare a parameter typed as the config `Model`. Umbod injects the saved, decrypted configuration at call time. The agent user never passes it. Put it after the real tool inputs; keep tool inputs as `Annotated[..., Field(description=...)]` so descriptions reach the MCP schema.

## Tools return raw JSON

Default to returning the API's JSON payload unchanged (`dict[str, Any]`). Only normalize if the user explicitly asked for it.

## Tests (mocked)

Two test modules, mirroring `tests/connectors/plugins/rejseplanen/`:
- `test_*_api_client.py` — mock the HTTP client; assert request params and that responses pass through unchanged.
- `test_*_configuration_check.py` — assert valid path returns `valid=True`, and rejected/unreachable paths return `valid=False` with the right `field_messages`.

No test performs a real network call or uses a real credential.
