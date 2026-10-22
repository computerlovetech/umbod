# Personal downstream MCP OAuth

## Delivery status

First delivery implemented and verified: ownership, persistence, and fail-closed integration. The [second iteration](personal-downstream-mcp-catalogue-specification.md) adds main-Umbod administrator preconfiguration and authenticated user catalogue/opt-in. The [third iteration](personal-downstream-mcp-authorization-specification.md) adds durable personal sign-in with default availability on securely configured deployments for a deliberately restricted provider subset. The [provider-policy iteration](personal-downstream-mcp-provider-policy-specification.md) adds administrator-approved scopes and preconfigured public/confidential clients. Runtime execution, refresh, capability discovery policy and UI remain planned work. Desktop is retired; historical verification below records the earlier delivery only.

## Target responsibility model

Administrators own approved MCP definitions, eligible groups, capabilities, scope limits, and organisation-wide disablement. Users own personal enablement, downstream authorization, and disconnection. Personal execution requires administrative publication, capability activation, group permission, personal enablement, and valid personal authorization. Shared service-account connections remain supported explicitly.

A canonical principal consists of a trusted identity namespace and stable subject. REST and MCP raw issuer/subject pairs must not be assumed equivalent: the MCP OAuth proxy can issue tokens under Umbod's public MCP URL while REST verifies upstream tokens. Email and OAuth client IDs are not ownership identifiers. Boundary identity equivalence is a release gate for personal execution.

## Local development identity

Only the `local`/`dev` runtime with development admin simulation, enabled personal connections and an exact nonempty `test:` namespace automatically uses the configured Admin Test User for personal identity. Default REST composition accepts tokenless `/api/me` requests by invoking the configured simulated verifier; caller tokens and forwarded identity headers cannot select another owner. Explicit user-verifier hooks remain token-required and never inherit the admin verifier. Personal MCP adapters require a current authenticated `single_test_user` context before projecting that same configured subject, profile and admin membership claim. Original machine claims are rejected; global MCP/shared/native claims and permissions are unchanged. A different MCP group claim receives no invented membership, and `simulated_admin=false` grants no simulated administrator membership. Production, real-provider, JWT and unauthenticated modes never receive this fallback.

Preserve both `UMBOD_ADMIN_SIMULATED_USER_ID` and `UMBOD_PERSONAL_CONNECTIONS_IDENTITY_NAMESPACE` across restarts to retain ownership; display names and email addresses are not ownership keys. An empty eligible catalogue is legitimate. Publication, explicit connector/tool grants, owner enablement, provider OAuth consent and explicit discovery remain mandatory; no shared credentials or root-secret generation are introduced.

## First delivery

- OAuth definitions expose `authorization_mode` as `shared` or `personal`. Legacy documents without the field remain shared.
- A new `core/connectors/downstream_mcp/personal_connections/` module owns validated principal, connection state, storage ports, in-memory implementation, and service operations.
- One additive encrypted persistence table stores principal-scoped connection state, including enablement, authorization presence, and an opaque revision.
- Core operations read a connection, set enablement, disconnect, and conditionally replace authorization. Missing connections are disabled and unauthorized. Enabling does not authorize; disabling retains authorization; disconnecting disables and removes authorization.
- Revisions prevent stale authorization writes after disconnect or replacement. Missing records cannot be recreated by conditional replacement.
- Connector deletion removes personal records transactionally.
- Existing shared execution, discovery, management, and OAuth paths reject personal definitions before accessing shared credentials or making downstream requests. Previously materialized capabilities must also fail closed.
- Public creation, modification, and execution of personal definitions remain unsupported until the later slices are complete.
- Existing shared OAuth and Desktop behavior remain unchanged.

## Acceptance criteria

### A1: Shared compatibility

Given an existing OAuth definition without an ownership field, when loaded and used, then it behaves as shared without creating personal state.

### A2: Ownership isolation

Given two principals using the same connector, when one changes enablement or authorization, then the other's state remains unchanged. Identical subjects in distinct canonical namespaces are separate owners.

### A3: Lifecycle

Given no personal connection, when enabled through the core contract, then it becomes enabled without authorization. Given authorization, when disabled, then authorization is retained. When disconnected, then the connection is disabled and authorization removed. Repeated lifecycle requests preserve their resulting state.

### A4: Persistence parity

Given identical operations against in-memory and encrypted persistent stores, when read, then observable state is equivalent. Saved state survives adapter recreation and authorization is encrypted at rest. Decrypted ownership is checked against the requested key.

### A5: Stale-write rejection

Given a revision preceding disconnect or authorization replacement, when used to conditionally replace authorization, then the write is rejected. Conditional replacement never creates a missing record.

### A6: No shared fallback

Given a personal definition, saved catalog, and valid shared credentials, when listed, searched, invoked directly, or accessed through a previously materialized handle, then no downstream request occurs. This applies to tools, prompts, resources, resource templates, and alternative exposure modes. Personal execution stays denied even if personal authorization exists.

### A7: Safe discovery and OAuth

Given a personal definition with shared credentials, when existing background discovery or shared OAuth operations target it, then no provider request or shared credential mutation occurs.

### A8: Unsupported public writes

Given a personal ownership request submitted to existing public create or update APIs, when validated, then it is rejected without partial persistence. Supported existing requests remain compatible.

### A9: Missing identity

Given no validated canonical principal, when personal state is requested, then access fails without reading or changing a record using an inferred identity.

### A10: Transactional deletion

Given personal records for a connector, when supported connector deletion succeeds, then all those records are removed. If deletion fails transactionally, no partial cleanup is committed.

## Implementation locations

Backend paths are relative to `umbod/api/src/umbod/`.

- New domain module: `core/connectors/downstream_mcp/personal_connections/` with `models.py`, `ports.py`, `service.py`, `inmemory.py`, public exports, and a responsibility index.
- Definition mode: `core/connectors/downstream_mcp/models.py`.
- Persistent adapter: `core/connectors/downstream_mcp/stores/personal_connections.py`; table registration in `stores/schema.py`, `stores/factory.py`, and `infrastructure/persistence/schema_preparation.py`.
- Transactional cleanup: downstream `management/aggregate_unit_of_work.py` and matching in-memory unit-of-work behavior.
- Ownership guards: downstream connection mapping, management preparation/update, runtime provider/client creation, discovery execution, and shared OAuth boundaries as required by actual call paths.
- Update affected core, MCP, and REST responsibility indexes.

No existing columns require alteration: ownership is part of the stored definition JSON and personal state uses a new table. Do not introduce a migration framework for this additive change. Personal writes must not be exposed during a mixed-version rollout with old workers.

## Subsequent deliveries

The second iteration supersedes A8's public-write restriction only through a separate, policy-gated personal creation endpoint. Existing shared creation/configuration contracts are not reinterpreted. It implements verified identity adapters, discovery-free definition creation and user selection endpoints; The third iteration adds durable OAuth-attempt endpoints and a state-bound callback without enabling execution.

Remaining delivery plan:

1. Principal-scoped runtime authorization resolution without connector-only credential caching; consistent tool/prompt/resource enforcement.
2. Extend verified identity integration into personal runtime resolution, including a deliberate stable development/test identity contract.
3. Extend the delivered durable OAuth coordinator with refresh concurrency and reconnect-required lifecycle; preserve explicit scope/client policy, one-time state, PKCE, atomic claims and revision-safe completion.
4. Extend the delivered `/api/me/connectors/mcp` authorization flow with refresh and reconnect status. The third iteration implements start/read/cancel attempts and `/api/oauth/downstream-mcp/callback`; no caller-supplied owner ID.
5. `/settings/connections` UI and admin personal-OAuth configuration; reusable user API and components separate from admin-only state.
6. Capability discovery policy: runtime access is the intersection of administrator-approved capabilities and those available to the downstream user. Administrative discovery credentials must never become user runtime credentials.

## Verification

Run shared store contract tests for both in-memory and persistent adapters, encryption/restart/ownership-tampering checks, stale-write races, missing-principal rejection, and cached capability denial. Re-run API/MCP unit tests, Python lint, shared Semgrep, and disposable Kind running-service verification. Desktop verification is no longer applicable. UI verification applies when the later frontend slice is implemented.

Baseline before implementation: 2,143 API tests and 161 Desktop tests pass; Ruff passes. Shared Semgrep reports 47 existing findings.

First-delivery verification: 2,218 API tests and 161 Desktop tests pass; Ruff passes in both packages. Disposable Kind installation/chart tests and all 23 live runtime tests pass. Shared Semgrep completes with the same 47 findings and no new findings. Review identified a cached template-resource read bypass; ownership-aware resource wrappers and a regression test close it. Personal connection tests cover both storage implementations, cross-owner isolation, encryption, stale writes, competing writes/disconnection, and transactional deletion rollback.
