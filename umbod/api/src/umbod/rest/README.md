# REST

**Module responsibility:** FastAPI boundary for administration, system, authentication, and user-facing HTTP behavior.

**Read when working with:** Routes, HTTP schemas, authentication middleware, dependency providers, API metrics, or application startup.

## Entry modules

### `main.py`, `factories.py`, and `dependencies.py`

**Read when working with:** Application startup, REST composition, dependency lifetimes, or adapter wiring.

## Submodules

### `authentication/`

**Read when working with:** Shared root REST authentication in `rest_middleware.py`, path classification in `rest_paths.py`, local identity policy in `local.py`, administrative membership, JWT handling, or the cookie mutation boundary in `csrf_middleware.py`.

`caller.py` adapts successfully verified JWT claims into an immutable shared caller context containing only authentication provenance and subject identity. The root middleware retains this request-local snapshot after authentication; mounted administration checks membership using those same accepted claims without verifying again or replacing provenance. Standalone administrator middleware retains its existing authentication and membership behavior. Provenance follows the actual verifier, never token claims; the adapter does not verify credentials. `deps.py:get_caller_context` rejects requests without that snapshot. Current-user identity consumes its subject while profile enrichment retains private verified claims; existing group and personal-identity parsers remain unchanged.

Personal identity dependencies capture typed facts from accepted claims and construct a narrow policy before invoking core resolution. They share claim/membership projection with MCP through the downstream feature adapters, not a REST-to-MCP import. `CallerContext` remains an observation; `CanonicalPrincipal` is the resolved business owner, with unchanged namespace/subject keys. Personal services receive a captured `PersonalCaller` containing the shared observation, separately resolved canonical owner and unqualified membership. The identity-required dependency resolves once and rejects unavailable authentication or identity before service construction. There is no deferred principal-provider compatibility path.

User catalogue capture separately projects immutable caller/membership, personal resolution and the precomputed opaque catalogue identity key. Catalogue assembly receives no raw claim dictionary; shared catalogue availability remains independent of personal mapping success.

Authentication and cookie safeguards cover the entire `/api` namespace at the root, including mounted documentation and subsequently added root routes. Path classification respects ASGI deployment prefixes. CORS remains outside the boundary; cookie mutation rejection precedes authentication, and administrator metrics include authentication failures. Callback secret redaction stays outermost. `/api/system/health` and the internal `/system` service contract remain public; telemetry retains its independent bearer contract outside `/api`. The dedicated public callback application retains generic and issuer-bound callback routes and sanitized 400 handling for noncanonical callback descendants and its disabled docs/OpenAPI paths; similarly named `callbackevil` paths are not exempt. Local explicit `disabled` mode bypasses administration only, never `/api/me` or other REST authentication. Production configuration rejects disabled/simulated REST modes and development authentication even with personal support disabled, including manually copied settings at REST startup.

Local REST identity is backend-owned: default simulation requires runtime profile `local`, runtime auth `dev`, simulation mode, development environment and a nonblank configured subject, independently of personal support or namespace validity. The root normalizes only this default simulated identity to issuer `urn:umbod:local`, retaining LOCAL_SIMULATION provenance and configured groups everywhere. Tokens and identity headers cannot change these facts. Personal canonical namespace/subject ownership remains unchanged; its local policy accepts this backend issuer as well as the existing issuer-absent MCP observation. Explicit user verifiers remain strict and administrator verifiers are independent. See [`personal_connections`](connectors/downstream_mcp/personal_connections/README.md).

## Administration client contract

`/api/admin` is the only administration API mount; legacy `/admin` API requests return 404 without redirects. Clients append resource paths such as `/users` or `/connectors/openapi/setup` to that base URL. Authentication and cookie safeguards apply to the canonical mount. `/api/admin/docs` and `/api/admin/openapi.json` require authentication; OpenAPI operation paths are relative to the mount's `servers` URL, including an upstream ASGI root prefix.

Native clients and cross-origin static SPAs send `Authorization: Bearer <JWT>`. The configured `admin_authentication.jwt_header_name` takes precedence when present, with Authorization used only when that header is absent. An empty or invalid selected header is rejected, never retried using another token. Identity at `/users` reuses verified access claims retained on request state after successful authentication and membership checks; request-scoped user dependencies supply optional profile enrichment. A gateway must strip client-supplied forwarded credential headers before supplying its own trusted value.

Production JWT verification requires RS256 signatures from the configured admin JWKS URL, an exact configured OIDC issuer and audience, and `iss`, `aud`, `exp`, and `sub` claims. Configure `UMBOD_OIDC_ISSUER_URL`, `UMBOD_OIDC_AUDIENCE`, and optionally `UMBOD_ADMIN_JWKS_URL`; empty issuer or audience prevents production admin startup. Membership must match `UMBOD_ADMIN_GROUP` in `UMBOD_ADMIN_MEMBERSHIP_CLAIM` (provider-derived when unset). Valid JWTs without required membership receive 403; invalid/missing tokens receive 401. `/users` requires a string subject from the verified token. Its required `email` response field is nullable: absent, null, or non-string email claims return `null` without changing authentication or membership policy. Profile fields never come from unverified forwarded identity headers. Optional verified ID-token enrichment and literal claim mappings follow the [user-profile configuration contract](../../../../docs/operations/configuration.md#optional-user-profile-enrichment). Development and simulation modes remain explicitly separate; MCP JWT verification is unchanged.

For a gateway exporting access tokens, set `UMBOD_ADMIN_JWT_HEADER` to its access-token header, for example `X-Auth-Request-Access-Token`. The selected token must be a JWT issued for the configured API audience. An ID token issued for a different web client audience, an opaque access token, or a token without the configured group claim is not compatible. The verifier does not infer token kind or accept arbitrary audiences; configuring a client-ID audience deliberately accepts tokens for that audience. These routes provide no OAuth or native login flow.

Administration requests carrying any Cookie header require both an exact trusted Origin and `X-Umbod-Web-Request: 1` for methods other than GET, HEAD, and OPTIONS. Trusted origins are the origin of `endpoints.site_base_url` (`UMBOD_PUBLIC_SITE_ORIGIN`) and explicitly listed `cors.origins` (`UMBOD_CORS_ORIGINS`); wildcard and null origins never grant cookie mutation access. Failed safeguards return 403 before mutation execution, including requests that also carry a bearer token. Cookies are gateway credentials, not authenticated directly by Python. Same-origin browser requests use gateway cookies and the marker; cookie-free bearer clients do not need the marker or Origin. CORS keeps `allow_credentials=False`: same-origin gateway cookies, cross-origin bearer requests.

`/system` remains the internal system application, including runtime state and events. Only `/api/system/health` is publicly aliased; no runtime state, event, or system documentation aliases are installed at `/api/system`.

### `connectors/`

**Read when working with:** Connector administration HTTP surface shared across kinds, plus kind-specific packages under `native/`, `openapi/`, and `downstream_mcp/`.

Shared root modules: kind-agnostic DI, shared schemas, invocation policy helpers, tool activation, publication status, and capability-description response mapping. `connectors/icons.py` provides request-scoped website favicon discovery, racing origin `/favicon.ico` and HTML icon links. MCP probes preserve advertised icons before invoking website discovery. Public-only, DNS-pinned lookups never send connector credentials; individual strategies have a one-second timeout and the overall discovery deadline is 1.5 seconds. Shared MCP probes preserve advertised icons and enrich missing icons during configuration and refresh. OpenAPI setup stores and exposes the discovered `icon_url`; legacy connector records use an empty URL. Personal MCP creation remains discovery-free.

Kind packages isolate kind-specific routes, schemas, and dependencies:

- `connectors/native/` — native catalog administration (`/connectors/catalog`)
- `connectors/openapi/` — OpenAPI connector administration, bounded JSON imports, and backend-owned setup (`/connectors/openapi`)

`POST /api/admin/connectors/openapi/setup` accepts required JSON fields `display_name`, `tool_name_prefix`, `capability_description`, `document` (object), `approved_hosts` (string array), `authentication_type` (`none` or `bearer`), and `bearer_token` (string, blank permitted only for `none`). It returns the existing `OpenApiConnectorResponse` with status 201. The request-scoped setup port validates the document, server/host selection, and bearer configuration before creating a connector, then imports and configures through the existing ports. The configured import byte limit applies to the whole JSON request, checked against Content-Length and streamed bytes before decoding.

Setup is compensated, not transactional: failures after creation attempt both credential clearing and connector deletion. Invalid setup returns 422 with `detail.code=openapi_setup_invalid_request`; operation failure after successful cleanup returns 500 with `detail.code=openapi_setup_failed`. Cleanup failure returns 500 with `detail.code=openapi_setup_cleanup_failed` and `detail.connector_id`, so operators can reconcile residual connector or credential state. Error bodies never reflect submitted documents or bearer secrets. Existing create/import/configuration APIs remain supported. Both SPA and native clients should use setup rather than coordinating creation and cleanup themselves. The core implementation is `core/connectors/openapi/management/setup.py`; its request and public ports are in `setup_ports.py`.
- [`connectors/downstream_mcp/`](connectors/downstream_mcp/README.md) — Downstream MCP administration (`/connectors/mcp`), including endpoint-only personal OAuth preconfiguration.

Downstream MCP responses also describe saved `oauth` authorizations. Shared OAuth administration lives in `connectors/downstream_mcp/oauth.py` under `/api/admin/connectors/mcp/oauth`: `GET /status`, `GET /{connector_id}`, and `POST /{connector_id}/{discover,begin,cancel,refresh,logout}`. Begin accepts optional `client_id` and `scopes`; omitted scopes preserve the saved choice. Details expose saved authorization, granted/requested/available scopes, registration mode, bounded redacted diagnostics, and separate authorization/discovery outcomes. Admin authentication and cookie safeguards apply to every route.

Deployment composition supplies an `OAuthService` through `umbod.hosting.create_rest_app`. The host implements shared storage, connector lookup, callback addresses, and transport reconnection ports; it does not implement OAuth policy. The composing host must close the service during shutdown. These shared host ports do not implement personal OAuth callbacks.

Without a configured host, these routes return `503` with `detail.code=oauth_host_unavailable`. This change does not enable browser sign-in in multi-worker Enterprise deployments: credential ownership and callback/session coordination must be supplied explicitly before enabling it. Saved server authorizations continue to use shared runtime/storage support in `core/connectors/downstream_mcp/adapters/fastmcp/oauth.py`.

OAuth definitions distinguish shared and personal ownership; omitted ownership remains shared. `POST /api/admin/connectors/mcp/personal-oauth` accepts existing metadata and endpoint-only configuration when `personal_connections.enabled` is enabled; disabled deployments return 404 with `personal_connections_unavailable`. Creation returns 201 without probing, shared credentials, catalogue, health, active capabilities or publication. Detail, summary and configuration responses expose `authorization_mode`; personal credentials always project as unconfigured. Existing personal metadata/configuration edits and ownership conversion remain rejected. Personal publication and deletion are supported, and published personal definitions become connector-level group permission targets without capabilities. When an OAuth host is configured, connector-specific admin OAuth routes reject persisted personal definitions with `409` and `detail.code=personal_oauth_unavailable` before calling that host. Hosts also declare OAuth connection ownership, and shared orchestration rejects personal ownership. Personal authorization uses a separate durable workflow, never the shared host. Its independently resolved scope, automatically available with configured prerequisites, is described in the [authorization specification](../../../../docs/operations/personal-downstream-mcp-authorization-specification.md); the [catalogue specification](../../../../docs/operations/personal-downstream-mcp-catalogue-specification.md) records the preceding iteration.

Administrator-approved personal tools are configured through `GET`/`PUT /api/admin/connectors/mcp/{id}/personal-tools`, separately from OAuth client policy. Schema changes reset tool activation and explicit capability grants; discovery does not grant either. Only administrator metadata enters the global catalogue. Personal user discovery remains private and principal-scoped.

### `connectors/downstream_mcp/personal_connections/`

`/api/me` is an always-mounted non-admin application authenticated at the shared root boundary with its independent verifier selection. Personal routes remain conditional on personal support; the general catalogue does not require canonical personal identity mapping. It reuses configured JWT verification and credential-header precedence without administrator membership checks. Missing/invalid credentials receive 401; personal routes reject a verified identity that cannot map to the configured canonical authority with 403 before personal state access. Cookie mutations require the same trusted Origin and web-request marker as administration. Documentation and OpenAPI require authentication. Unexpected request failures, including dependency construction and response serialization, return a fixed sanitized 500 response with `Cache-Control: no-store` from the mounted application's exception boundary; known HTTP and domain failures retain their existing contracts.

`GET /api/me/connectors/mcp` and `GET /api/me/connectors/mcp/{id}` expose eligible published personal definitions with explicit connector grants through the caller's `mcp.permission_group_claim`. `PUT /api/me/connectors/mcp/{id}/enablement` accepts a strict boolean `enabled`; `DELETE /api/me/connectors/mcp/{id}/authorization` disconnects with 204. No request accepts an owner or credential. Projections expose enablement and authorization presence, never endpoint details, revisions or secrets; `runtime_available` remains false with reason `personal_oauth_not_supported`.

Withdrawal hides catalogue/detail/enable=true access. Users with existing personal records can still disable/disconnect while the definition exists; users without a record cannot use cleanup to inspect an ineligible definition. `dependencies.py` creates request-scoped identity, lifecycle and inventory objects. Production personal mutations validate the definition in the same serialized transaction as their write, preventing resurrection after concurrent deletion. The [local index](connectors/downstream_mcp/personal_connections/README.md) lists responsibilities.

When `personal_connections.oauth_enabled` is also enabled, owner-scoped POST/GET/DELETE authorization-attempt routes under `/api/me/connectors/mcp/{id}/oauth/attempts` coordinate durable personal sign-in. The independently mounted `/api/oauth/downstream-mcp/callback` is public but protected by expiring one-time state, PKCE and issuer binding; it never obtains ownership from callback parameters. Its query secrets are removed from the request scope before access logging. Authorization does not enable personal runtime execution. Preparation, exchange and completion do not update shared credentials or discover capabilities.

`POST /api/me/connectors/mcp/{id}/tools/discovery` accepts only an empty JSON object. It requires the owner's usable authorization and current connector eligibility, checks discovered contracts against administrator approval and commits encrypted owner-bound observations only after rechecking eligibility. Success is a no-store 204; it does not enable runtime execution.

### `groups/`

**Read when working with:** Neutral shared group catalogue administration at `/api/admin/groups`. The [local index](groups/README.md) describes exact ID registration, usage-checked deletion and request-scoped persistence composition.

### `mcp_permissions/`

**Read when working with:** Group-to-tool permission APIs and permission events.

### `capability_descriptions/`

**Read when working with:** Capability description overrides exposed through the API.

### `instance_configuration/`

**Read when working with:** Resolved instance configuration exposed to clients.

### `telemetry/`

**Read when working with:** OTLP JSON logs, metrics, and traces ingestion, dedicated bearer authentication, bounded gzip requests, or stdout export logging.

### `metrics/` and `system/`

**Read when working with:** API observability or health endpoints.

### `filesystem_administration/`

Authenticated admin GET/PUT `/api/admin/filesystem/root-access` supports read-only status inspection and revision-checked direct root GROUP editing, including clean initialization without CLI use. Existing admin membership, simulation and cookie CSRF rules apply; ordinary filesystem access remains separately authorized through strict verified identity or the explicit local-development resolver. See the [local index](filesystem_administration/README.md).

### `filesystem/`

Always-mounted authenticated `/api/me/filesystem` browsing and empty creation, independent of personal support. The [`planned` endpoint index](filesystem/planned/README.md) records identity-verified no-store 501 placeholders and the planned multipart upload contract; it adds no item lookup, content access or writes. UUID-only routes expose safe node summaries, strict name/metadata creation requests and fixed sanitized domain errors. Request-scoped dependencies capture accepted caller/group observations and inject the strict core verified identity resolver, or opt into exact backend-configured local simulation under the shared local/dev policy. Local simulation remains LOCAL_SIMULATION, never upstream-verified; no grants or root ownership are implicit. MCP retains its strict resolver. Existing user no-store and cookie safeguards apply. See the [local index](filesystem/README.md).

### `user_catalogue/`

**Read when working with:** Always-mounted `GET /api/me/catalogue`, safe cross-kind user projections, opaque identity keys, personal-source gating and collision filtering. The [local index](user_catalogue/README.md) describes dependencies and contracts. The `/api/me` app authenticates catalogue and documentation independently of administrator membership; existing personal routes remain conditional on personal support.

### `users/`

**Read when working with:** Current-user identity, optional profile enrichment, or claim mapping. `profiles.py` defines the typed provider port and in-memory adapter; `mapping.py` normalizes literal claims; `id_token.py` verifies and binds enrichment; `current_user.py` coordinates the unchanged response; `deps.py` assembles request-scoped providers. `signing_keys.py` defines the infrastructure resolver/source seams; `jwks.py` implements a protected shared cache owned by the root app lifespan. The lifespan yields a state mapping that Starlette propagates into `request.state`; typed mounted-admin dependencies retrieve the resolver there without storing dependencies on `app.state`. Profile key fetches run in the synchronous `/users` handler's threadpool, not on the event loop. `authentication/deps.py` retrieves middleware-verified access claims. Authentication debug logging records only fixed credential-presence booleans, never header values or decoded claims.

## Embedded host composition

Supported hosts use [`umbod.hosting`](../hosting/README.md), including `create_rest_app`. `main.py:create_app` remains the unchanged legacy compatibility entrypoint. The service factory is `umbod.hosting.rest_service:create_app`.

The `admin_verifier` hook on `create_rest_app` supplies the same deployment verifier to administration middleware and the request-scoped current-user dependency. The separate optional `user_verifier` hook applies only to `/api/me`; omitting it uses configured verification, never the administrator override. Normal verifier selection and profile enrichment remain unchanged.
