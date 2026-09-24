# Connectors

**Module responsibility:** Public Python API for users building connectors that are deployed in Umbod and exposed as configurable MCP capabilities.

**Read when working with:** Connector packages, public connector contracts, configuration models, capability declarations, or plugin discovery. Use `skills/draft-agent-connector/SKILL.md` as the connector-authoring workflow and contract reference. Use the SDK package-level `README.md` for distribution packaging, entry-point registration, installation, and deployment enablement.

## Submodules

### `api/`

**Read when working with:** Public connector, capability, parameter, configuration, and registration contracts.

## Modules

### `plugin_api.py`

**Read when working with:** The public imports and types exposed to connector authors.

### `discovery.py` and `registry.py`

**Read when working with:** Connector package discovery, loading, validation, or registration.

### `proxies.py`

**Read when working with:** Public model and field abstractions provided to connector packages.

### `uploaded_file.py`

**Read when working with:** Request-lifetime file input data exposed through `plugin_api.UploadedFile`.

A file-input tool must expose exactly one required `UploadedFile` parameter and no other public parameters. It may also declare the hidden injected `configuration` parameter. File-input tools currently require flat MCP exposure mode; gateway and codemode registration reject them.
