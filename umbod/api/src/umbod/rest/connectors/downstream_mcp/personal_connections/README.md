# Personal connections REST

Downstream MCP-owned delivery for authenticated user selection under `/api/me`, separate from administrator authorization. The public OAuth callback remains independently state-bound. Package nesting does not change URLs, middleware or mounts.

- `routes.py`: eligible catalogue, personal state, strict enablement and disconnect endpoints.
- `schemas.py`: secret-free user projections with truthful current-owner runtime status.
- `runtime.py`: request-scoped current-context/runtime composition. Selection responses check current approved, observed, activated and granted tools in storage without discovery or network calls; disabled profiles remain unavailable.
- `dependencies.py`: request-scoped canonical principal, verified group membership and inventory composition through core ports and the shared persistence runtime. Verified identity mapping uses `VerifiedClaimsPrincipalProvider` from `core/connectors/downstream_mcp/personal_connections`.
- `oauth_routes.py` and `oauth_schemas.py`: bounded strict initiation bodies, safe attempt projections and owner-scoped status/cancellation.
- `oauth_dependencies.py`: request-scoped provider resources and authorization/callback service composition.
- `oauth_callback.py`: strict public callback parsing, namespace query redaction and fixed secret-free responses.
- `tools.py`: authenticated strict-empty `POST /connectors/mcp/{id}/tools/discovery`, request-scoped transport/service composition and fixed secret-free failures. Discovery uses only the verified owner's authorization and saves encrypted approved-contract intersections; it never approves tools, updates global user-derived metadata or executes them.
- `__init__.py`: router export.

`rest/main.py` mounts this application when the resolved personal identity policy is enabled. Operator configuration enables it automatically once a namespace and safe authentication are supplied; explicit `false` opts out. Authentication-only middleware verifies credentials once and retains claims on request state; identity mapping rejects unmappable claims before personal storage access. Cookie safeguards are identical to administration, but administrator membership is not required or sufficient for catalogue eligibility.

Published personal definitions require connector-level grants through the configured MCP permission group claim. Unpublished, ungranted and shared definitions are hidden. Existing owners can disable or disconnect retained connections after approval withdrawal; cleanup never exposes an ineligible definition to users without an existing record.

Personal authorization routes and callback dependencies live alongside the selection routes and use `core/connectors/downstream_mcp/personal_connections/oauth_service.py`. Their resolved `oauth_enabled` policy defaults on when selection, persistent SQLite and encryption are configured, unless explicitly opted out. User enablement and downstream consent remain explicit. POST starts a durable attempt with a strict empty body; owner-scoped GET and DELETE read/cancel it. A separately mounted public callback uses persisted one-time state, PKCE and issuer binding, not authenticated browser identity or a worker-local Future. Fixed no-store responses do not reflect provider parameters, and callback query secrets are redacted before access logging.

There is no user-supplied owner, credential upload, scope/client override, or return URL. Personal OAuth remains unavailable to shared runtime and discovery paths, even after successful authorization.
