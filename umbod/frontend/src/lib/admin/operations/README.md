# Browser Administration Operations

**Module responsibility:** Typed administration mutation handlers receiving an injected `AdminApi` and prepared form data, without server events or form-action network requests.

- `contracts.ts` defines operation handlers, failures, and navigation results.
- `connectors.ts`, `downstream-mcp-connectors.ts`, `openapi-connectors.ts`, and `group-permissions.ts` preserve bounded-context validation, safe failure values, publication, and authoritative reconciliation.
- `browser-submit.ts` dispatches explicit operation names, respects form cancellation and submitter overrides, invokes result/update callbacks, and always runs registered completion cleanup. Its dependencies are injectable for behavioral tests.
- `operation-state.svelte.ts` holds SPA submission feedback owned by route and connector, cleared when the navigation location changes. Disposed forms and obsolete selections cannot publish completion feedback or reconciliation.

OpenAPI setup parses and validates JSON files before one `POST /admin/connectors/openapi/setup` request. The response uses `openApiConnectorSchema`. Cleanup failures expose the connector identity and block retry in the setup modal. Configuration retains its metadata/authentication/import sequencing and partial-failure messaging.
