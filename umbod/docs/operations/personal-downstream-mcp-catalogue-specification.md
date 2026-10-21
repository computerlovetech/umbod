# Personal MCP catalogue and opt-in

## Status

Second iteration implemented and verified. Main Umbod only; the removed Desktop product is out of scope and its deletions were preserved. Personal downstream OAuth login and execution remain disabled in this iteration. The subsequent [authorization iteration](personal-downstream-mcp-authorization-specification.md) adds durable login without enabling execution. Personal feature availability now defaults on when the identity and storage/security prerequisites are configured, with explicit deployment opt-out; per-user opt-in remains mandatory.

## Goal

Deliver administrator preconfiguration, approval and group eligibility, followed by authenticated non-administrator personal selection through REST. Enabling expresses user intent; it does not establish OAuth authorization or enable runtime execution.

## Administrative contract

- Add `POST /api/admin/connectors/mcp/personal-oauth` with the existing metadata shape and endpoint-only configuration. Reject submitted credentials and owner identifiers.
- Add an explicit `CreatePersonalOAuthConnectorDefinition` core operation and `create_personal_oauth()` creator method. Keep the existing shared creation union unchanged. Generate the ID, enforce ID/public-path uniqueness, and create the definition atomically without probing or making downstream requests.
- New definitions are OAuth/personal, unpublished, without shared credentials, catalogue, health, or active capabilities.
- Existing publication endpoints approve or withdraw personal definitions without requiring discovery. Shared publication requirements remain unchanged.
- Published personal definitions become assignable connector-level group-permission targets even without discovered capabilities. Do not invent capabilities or relax runtime readiness.
- Administrative detail/summary/configuration projections expose shared/personal ownership. Personal `credential_configured` is false regardless of legacy shared records.
- Personal metadata/configuration edits and ownership conversion remain rejected until safe invalidation is implemented. Delete and publication remain supported.

## Identity and authenticated user boundary

Add an authenticated sibling application at `/api/me`, not an administrator-authorized route. Reuse the deployment JWT verifier mechanics, header precedence and cookie safeguards; preserve `/api/admin` membership enforcement. A separately named user-verifier composition hook must not inherit an administrator verifier implicitly.

Canonical ownership uses a validated deployment identity policy with an operator-controlled authority namespace. The same policy must be reusable for REST and MCP. Google and Auth0 use verified nonblank string `sub`; Entra uses verified `oid` with matching configured `tid`, not its application-specific `sub`. Do not use email, client ID, nested unverified aliases, or the outer MCP proxy issuer. Current FastMCP proxy access-token context normally contains upstream verified claims; Google may omit `iss` there.

Personal endpoints are unavailable when identity policy is disabled. Missing/invalid credentials return 401; authenticated but unmappable identity returns 403 before personal-store access. Insecure development/simulation policies must be explicitly isolated to test namespaces. Unauthenticated deployments must not acquire a synthetic owner. Production must reject incomplete identity policy configuration.

## User REST contract

- `GET /api/me/connectors/mcp`: eligible personal catalogue, sorted by connector ID.
- `GET /api/me/connectors/mcp/{id}`: caller's safe projection for an eligible definition.
- `PUT /api/me/connectors/mcp/{id}/enablement`: strict boolean `enabled`.
- `DELETE /api/me/connectors/mcp/{id}/authorization`: disconnect, return 204.

A definition is eligible only if personal, published, and explicitly connector-granted through the caller's verified groups. Administrator membership alone grants no personal access. Existing capability grants remain execution policy, not selection eligibility.

Responses include connector ID, display name, effective description, enablement, authorization presence, `runtime_available=false`, and an explicit not-yet-supported reason. Never return tokens, encrypted documents, internal revisions, owner IDs, or endpoint configuration. Reject any caller-supplied owner or credential fields.

After publication or group eligibility is withdrawn, omit the definition from inventory and return 404 for detail and enable=true. Disable and disconnect remain available to the owner while the personal definition exists, so users can clean up retained state. Shared or deleted definitions return 404. The personal lifecycle store's encryption, isolation, stale-write rejection and deletion cleanup remain unchanged.

## Acceptance scenarios

### C1: Preconfiguration

Given an authenticated administrator, when a valid personal definition is created, then return 201 with personal ownership, unpublished status, unknown health and no shared credentials; no login, discovery or downstream request occurs.

### C2: Approval and assignment

Given a personal definition without a catalogue, when published, then it becomes an assignable connector target. Shared definitions still require valid discovered capabilities for publication.

### C3: Non-admin selection

Given published personal definitions and connector grants for a non-admin's verified groups, when requesting the personal catalogue, then only eligible definitions appear. A new connection is disabled and unauthorized; enabling it changes only that user's state and remains runtime-unavailable.

### C4: Ownership and presentation

Given two users selecting the same definition, when one changes state, then the other's state is unaffected. Responses expose no credentials, revisions or endpoint details. Equal subjects under separate configured namespaces remain separate owners.

### C5: Revocation and cleanup

Given an enabled connection, when its approval or connector grant is removed, then inventory/detail/enable=true deny access, while disable/disconnect remain owner-accessible. Disconnect clears local authorization without a downstream request.

### C6: Authentication

Given missing/invalid credentials, when calling user routes, then return 401. Given verified but unmappable claims, then return 403 before personal-store access. Configured credential-header precedence and cookie Origin/marker protection remain enforced. Non-admins remain forbidden from admin routes.

### C7: Identity parity

Given provider-verified REST and MCP claims for the same account and configured authority, when mapped, then canonical ownership keys match. Entra app-specific subjects do not affect a stable tenant/object mapping. Missing, malformed, mismatched-tenant and machine-only identities are rejected; no email or client-ID fallback exists.

### C8: Safety and compatibility

Given legacy shared connectors, when used after this change, then behavior remains unchanged. Personal discovery, shared OAuth and runtime execution remain denied, including cached handles. Unsupported personal edits/ownership changes fail atomically. Connector deletion removes personal state transactionally.

## Implementation structure

Extend the existing downstream personal-connections module with inventory/eligibility orchestration; extend management and publication with explicit personal definition support; add a downstream permission-catalog decorator. Use `rest/connectors/downstream_mcp/personal_connections/` for user projections, dependencies and routes, independently mounted from administrator delivery. Keep identity mapping policy outside transport-specific claim extraction and create request-scoped application objects. Register no new database tables for this slice.

Document the new configuration and routes in affected README indexes and operation references. No frontend or published Helm chart changes are included. Test-only Kind values enable the personal policy and align the API/MCP permission group claim. Deployment must not allow personal writes while older workers remain active.

Production factory-created personal stores validate definition existence and personal ownership inside each mutation's serialized transaction. This closes the eligibility-check/deletion/write race without adding a schema. Standalone detached store contracts remain supported. Cleanup after eligibility withdrawal requires an existing personal record unless the caller is still eligible, preventing metadata enumeration through cleanup routes.

## Verification

Use public-port tests for personal inventory/lifecycle, administrator REST creation/publication/grants, authenticated non-admin access, cross-user isolation, withdrawal/cleanup, identity mapping parity, rejected claims/header precedence/CSRF, and zero downstream requests. Run API/MCP regression tests, Ruff, shared Semgrep, and disposable Kind running-service integration tests. Desktop checks no longer apply.

Verified results: 2,300 API/MCP tests passed, one existing empty Desktop-path parametrization skipped; Ruff passed. Disposable Kind installation/chart tests and all 24 live runtime tests passed, including the new admin-preconfiguration-to-user-opt-in flow without downstream login. Shared Semgrep completed with the same 47 existing findings and no new findings. Review-confirmed production/development verification classification and concurrent-deletion issues were fixed and regression-tested. Initial integration runs caught test-module name collisions and a test-fixture group-claim mismatch; both were corrected before the successful final runs.

The original delivery required feature opt-in. Current operator configuration defaults to automatic exposure once `UMBOD_PERSONAL_CONNECTIONS_IDENTITY_NAMESPACE` and safe authentication are supplied; `UMBOD_PERSONAL_CONNECTIONS_ENABLED=false` explicitly opts out. Development verification is restricted to explicit `test:` namespaces and rejected under a production profile. Runtime execution, browser authorization/callback coordination, token refresh and UI remain subsequent work.
