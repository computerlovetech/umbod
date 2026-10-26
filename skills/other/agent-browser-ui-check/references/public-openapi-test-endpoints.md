## Public OpenAPI Test Endpoints

The following public APIs can be used to test compatibility with different OpenAPI specification versions. Basic operations require no authentication.

### Swagger 2.0 (OpenAPI 2.0)

- **Specification:** https://petstore.swagger.io/v2/swagger.json
- **API Base URL:** https://petstore.swagger.io/v2
- **Test endpoint:** `GET /pet/findByStatus?status=available`
- **Purpose:** Validate support for Swagger 2.0 specifications, including `definitions`, `host`, `basePath`, and parameter definitions.

### OpenAPI 3.0

- **Specification:** https://petstore3.swagger.io/api/v3/openapi.json
- **API Base URL:** https://petstore3.swagger.io/api/v3
- **Test endpoint:** `GET /pet/findByStatus?status=available`
- **Purpose:** Validate support for OpenAPI 3.0 specifications, including `components/schemas`, `servers`, and `requestBody`.

### OpenAPI 3.1

- **Example specification:** https://sandbox.scalar.com/e/iycfn
- **Live API:** Not verified
- **Purpose:** Validate OpenAPI 3.1 parsing, including JSON Schema 2020-12 compatibility, nullable types, and webhooks.
- **Note:** Suitable for specification parsing tests; not verified for unauthenticated HTTP execution.

### Test Procedure

1. Retrieve each OpenAPI specification.
2. Parse and validate the specification.
3. Discover available operations and their input/output schemas.
4. Execute an unauthenticated GET request where a live endpoint is available.
5. Validate the HTTP response against the declared schema.
6. Verify that version-specific OpenAPI constructs are handled correctly.

**Expected result:** The service successfully parses each supported specification version, discovers its operations, and executes public endpoints without requiring authentication.
