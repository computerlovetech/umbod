---
name: draft-agent-connector
description: Use when a developer wants to build, draft, or add an Umbod connector for an external API or service. Guides authoring a connector plugin package against the connectors interface, with a Pydantic config, a live configuration check, tool functions, and mocked tests.
---

# Draft Agent Connector

Author one connector plugin implementation against the `umbod_sdk.connectors.plugin_api` interface. The user has the connector module, not the whole Umbod app: do **not** touch `pyproject.toml`, connector deployment configuration, Docker Compose, or MCP runtime — packaging and deployment are a separate integration step. Stop when the connector implementation is written and its mocked tests pass.

Read [REFERENCE.md](REFERENCE.md) for the exact interface before writing code. For the subsequent distribution packaging, `umbod.connectors` entry-point declaration, installation, and deployment-enablement steps, read `packages/umbod-connector-sdk/README.md` from the repository root.

## Steps

1. **Find the real schema**
   Do not build from pasted docs alone. Look for a machine-readable source: a live OpenAPI/Swagger endpoint, WADL, XSD, or a Postman collection. Confirm base URL, auth mechanism, response format, and the exact endpoints for the wanted tools from that source.
   Completion criterion: base URL, auth type, and each candidate endpoint's request/response shape are confirmed from an authoritative source, with any gap listed explicitly.

2. **Decide the v1 shape**
   Choose the smallest useful tool set (≤5) tied to what the user wants their agent to do, the config fields (secrets as `SecretStr`), and one safe live-check endpoint that proves the credential without creating, sending, or changing data.
   Completion criterion: the tool list, config fields, and the live-check endpoint are named, and output is confirmed raw-passthrough unless the user asked otherwise.

3. **Write the package**
   Create the plugin following the [REFERENCE.md](REFERENCE.md) shape: `admin_configuration.py` (config `Model`), `api_client.py` (HTTP + typed errors), `configuration_check.py` (live check), and `__init__.py` (`Connector(...)`, `@connector.configuration_check`, `@connector.tool(...)`). Each tool declares `configuration: <YourConfigModel>` as an injected parameter — never a caller argument. Connector icons are optional, but when provided they must be SVG files referenced by their `.svg` path; PNG, JPEG, WebP, ICO, and other formats are not supported.
   Completion criterion: every planned tool and the config check are implemented against the interface, with no reference to app wiring, deployment, or docker.

4. **Test with mocked HTTP**
   Write unit tests that mock the HTTP client — no real credentials, no live calls. Cover the config check's valid and invalid paths and each tool's request building and response passthrough. Run them.
   Completion criterion: the tests import the connector package and pass; no test performs a real network call.

## Rules

- Never request or hardcode an API key; the admin enters it in Umbod later.
- Only use SVG connector icons. Other image formats are unsupported and prevent the connector from loading.
- Return the API's raw JSON unless the user explicitly asked for normalized output.
- If schema facts are missing, write the package with explicit `TODO` gaps rather than inventing endpoints or fields.
- Do not add entry points, deployment availability, or run the app. Delivery and integration are out of scope for this skill.
