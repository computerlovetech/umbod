# OpenAPI connectors UI testing

Use the browser verification checklist in `browser-verification.md` for interaction, runtime health, evidence, and reporting. Follow the repository's setup instructions for the running app.

## Choose the API

- If the task supplies a specification URL and API base URL, use those values. Confirm authentication requirements and limit execution to authorized, non-destructive operations.
- If public compatibility testing is requested or no live API is supplied, read `public-openapi-test-endpoints.md` and select the specification version relevant to the task.
- For parsing-only work, verify specification loading and operation/schema discovery without requiring HTTP execution.
- OpenAPI 3.1's listed API is unverified: use it for parsing checks only, and report live execution as unverified unless a working endpoint is independently confirmed.

## Verify through the UI

1. Open the affected connector creation or configuration flow.
2. Configure the selected specification and API base URL using the available controls.
3. Verify that discovered operations and input/output schemas match the selected specification.
4. Where the UI supports execution and a live API is available, execute an authorized GET operation and verify the displayed response and any available schema-validation result.
5. Check validation and failure states relevant to the change, without treating an unavailable public API as proof of a connector defect.

## Report coverage

Record the specification version, specification URL, API base URL, operation, observed UI behavior, and runtime health. Distinguish parsing/discovery results from live execution and response-schema validation. Report unavailable endpoints, unsupported UI steps, and checks not performed explicitly; do not claim full compatibility from a single successful request.
