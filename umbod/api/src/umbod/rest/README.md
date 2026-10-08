# REST

**Module responsibility:** FastAPI boundary for administration, system, authentication, and user-facing HTTP behavior.

**Read when working with:** Routes, HTTP schemas, authentication middleware, dependency providers, API metrics, or application startup.

## Entry modules

### `main.py`, `factories.py`, and `dependencies.py`

**Read when working with:** Application startup, REST composition, dependency lifetimes, or adapter wiring.

## Submodules

### `authentication/`

**Read when working with:** Administrative authentication, JWT handling, local authentication simulation, or the cookie mutation boundary in `csrf_middleware.py`.

## Administration client contract

`/api/admin` is the only administration API mount; legacy `/admin` API requests return 404 without redirects. Clients append resource paths such as `/users` or `/connectors/openapi/setup` to that base URL. Authentication and cookie safeguards apply to the canonical mount. `/api/admin/docs` and `/api/admin/openapi.json` require authentication; OpenAPI operation paths are relative to the mount's `servers` URL, including an upstream ASGI root prefix.

Native clients and cross-origin static SPAs send `Authorization: Bearer <JWT>`. The configured `admin_authentication.jwt_header_name` takes precedence when present, with Authorization used only when that header is absent. An empty or invalid selected header is rejected, never retried using another token. Identity at `/users` uses the same selection and verifier. A gateway must strip client-supplied forwarded credential headers before supplying its own trusted value.

Production JWT verification requires RS256 signatures from the configured admin JWKS URL, an exact configured OIDC issuer and audience, and `iss`, `aud`, `exp`, and `sub` claims. Configure `UMBOD_OIDC_ISSUER_URL`, `UMBOD_OIDC_AUDIENCE`, and optionally `UMBOD_ADMIN_JWKS_URL`; empty issuer or audience prevents production admin startup. Membership must match `UMBOD_ADMIN_GROUP` in `UMBOD_ADMIN_MEMBERSHIP_CLAIM` (provider-derived when unset). Valid JWTs without required membership receive 403; invalid/missing tokens receive 401. `/users` requires a string subject from the verified token. Its required `email` response field is nullable: absent, null, or non-string email claims return `null` without changing authentication or membership policy. Profile fields never come from forwarded identity headers; no namespaced claim mapping is performed. Development and simulation modes remain explicitly separate; MCP JWT verification is unchanged.

For a gateway exporting access tokens, set `UMBOD_ADMIN_JWT_HEADER` to its access-token header, for example `X-Auth-Request-Access-Token`. The selected token must be a JWT issued for the configured API audience. An ID token issued for a different web client audience, an opaque access token, or a token without the configured group claim is not compatible. The verifier does not infer token kind or accept arbitrary audiences; configuring a client-ID audience deliberately accepts tokens for that audience. These routes provide no OAuth or native login flow.

Administration requests carrying any Cookie header require both an exact trusted Origin and `X-Umbod-Web-Request: 1` for methods other than GET, HEAD, and OPTIONS. Trusted origins are the origin of `endpoints.site_base_url` (`UMBOD_PUBLIC_SITE_ORIGIN`) and explicitly listed `cors.origins` (`UMBOD_CORS_ORIGINS`); wildcard and null origins never grant cookie mutation access. Failed safeguards return 403 before mutation execution, including requests that also carry a bearer token. Cookies are gateway credentials, not authenticated directly by Python. Same-origin browser requests use gateway cookies and the marker; cookie-free bearer clients do not need the marker or Origin. CORS keeps `allow_credentials=False`: same-origin gateway cookies, cross-origin bearer requests.

`/system` remains the internal system application, including runtime state and events. Only `/api/system/health` is publicly aliased; no runtime state, event, or system documentation aliases are installed at `/api/system`.

### `connectors/`

**Read when working with:** Connector administration HTTP surface shared across kinds, plus kind-specific packages under `native/`, `openapi/`, and `downstream_mcp/`.

Shared root modules: kind-agnostic DI, shared schemas, invocation policy helpers, tool activation, publication status, and capability-description response mapping.

Kind packages isolate kind-specific routes, schemas, and dependencies:

- `connectors/native/` — native catalog administration (`/connectors/catalog`)
- `connectors/openapi/` — OpenAPI connector administration, bounded JSON imports, and backend-owned setup (`/connectors/openapi`)

`POST /api/admin/connectors/openapi/setup` accepts required JSON fields `display_name`, `tool_name_prefix`, `capability_description`, `document` (object), `approved_hosts` (string array), `authentication_type` (`none` or `bearer`), and `bearer_token` (string, blank permitted only for `none`). It returns the existing `OpenApiConnectorResponse` with status 201. The request-scoped setup port validates the document, server/host selection, and bearer configuration before creating a connector, then imports and configures through the existing ports. The configured import byte limit applies to the whole JSON request, checked against Content-Length and streamed bytes before decoding.

Setup is compensated, not transactional: failures after creation attempt both credential clearing and connector deletion. Invalid setup returns 422 with `detail.code=openapi_setup_invalid_request`; operation failure after successful cleanup returns 500 with `detail.code=openapi_setup_failed`. Cleanup failure returns 500 with `detail.code=openapi_setup_cleanup_failed` and `detail.connector_id`, so operators can reconcile residual connector or credential state. Error bodies never reflect submitted documents or bearer secrets. Existing create/import/configuration APIs remain supported. Both SPA and native clients should use setup rather than coordinating creation and cleanup themselves. The core implementation is `core/connectors/openapi/management/setup.py`; its request and public ports are in `setup_ports.py`.
- `connectors/downstream_mcp/` — Downstream MCP administration (`/connectors/mcp`)

Downstream MCP responses also describe saved `oauth` authorizations. Interactive
sign-in is currently a Local-only host extension (`umbod/oauth.py`), not an
Enterprise admin route. Shared runtime/storage support lives in
`core/connectors/downstream_mcp/adapters/oauth.py`; Enterprise account ownership
and multi-worker sign-in coordination remain undecided.

### `mcp_permissions/`

**Read when working with:** Group-to-tool permission APIs and permission events.

### `capability_descriptions/`

**Read when working with:** Capability description overrides exposed through the API.

### `instance_configuration/`

**Read when working with:** Resolved instance configuration exposed to clients.

### `telemetry/`

**Read when working with:** OTLP JSON logs, metrics, and traces ingestion, dedicated bearer authentication, bounded gzip requests, or stdout export logging.

### `metrics/`, `system/`, and `users/`

**Read when working with:** API observability, health endpoints, or current-user behavior.
