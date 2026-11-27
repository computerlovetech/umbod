# Portable single-file connectors

Use this format for connector source that can be exercised offline in CPython and is intended to be portable to Monty. Uploading or running portable connectors in Umbod is not yet supported. For an installed Pydantic plugin, use the [trusted plugin reference](trusted-plugin.md) instead.

## Declare the connector

- Import `Connector` from `umbod_sdk.connectors` and create a module-level connector. Supply `id`, `name`, `description`, `capability_description`, and `configuration`. Set `configuration` to a JSON Schema dictionary, not a Pydantic model. Declare only settings the handlers need.
- Register one `@connector.configuration_check` and at least one `@connector.tool`. Give each tool a unique explicit `name`, a `description`, and an `input_schema` dictionary. Put public argument names, types, descriptions, and required fields in that schema. Use `output_schema` when declaring a contract for the tool's own result.
- Accept `configuration` as an injected keyword wherever the handler needs settings. Do not expose it in the public tool schema. HTTP-enabled connectors also receive an injected `context`; follow the [portable HTTP reference](portable-http.md) for that format.
- Export the contract using `connector.manifest()`, not `registration()`. Manifest version 1 applies without HTTP targets; a nonempty `http_targets` declaration opts into version 2. Portable manifests do not include prompts, resources, icons, or extensions.

## Verify offline

Check that `manifest()` succeeds, is JSON-serializable, and describes the expected tools and schemas. Call the decorated handlers directly with controlled inputs and configuration to test their behavior; manifest export does not validate individual invocations. Keep the connector independent of Umbod application internals and installed-plugin dependencies. Never use live credentials in a test.
