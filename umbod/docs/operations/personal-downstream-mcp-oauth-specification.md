# Personal downstream MCP OAuth

## Delivery status

First delivery implemented and verified: ownership, persistence, and fail-closed integration. The [second iteration](personal-downstream-mcp-catalogue-specification.md) adds main-Umbod administrator preconfiguration and authenticated user catalogue/opt-in. The [third iteration](personal-downstream-mcp-authorization-specification.md) adds durable personal sign-in with default availability on securely configured deployments for a deliberately restricted provider subset. The [provider-policy iteration](personal-downstream-mcp-provider-policy-specification.md) adds administrator-approved scopes and preconfigured public/confidential clients. Runtime execution, refresh, capability discovery policy and UI remain planned work. Desktop is retired; historical verification below records the earlier delivery only.

## Target responsibility model

Administrators own the personal MCP server allowlist, eligible groups, OAuth scope/client policy and organisation-wide withdrawal. Users own personal enablement, downstream authorization, explicit discovery and disconnection. Publication, a current connector-level group grant, owner enablement and valid owner authorization permit discovery and use of all tools available to that downstream user. No personal per-tool approval, activation or capability grant is required; server permission includes tools added later and obtained through explicit rediscovery. Shared/native activation and capability permissions remain unchanged. Discovery stores complete validated descriptors privately per owner, not in a global administrator catalogue.

A canonical principal consists of a trusted identity namespace and stable subject. REST and MCP raw issuer/subject pairs must not be assumed equivalent: the MCP OAuth proxy can issue tokens under Umbod's public MCP URL while REST verifies upstream tokens. Email and OAuth client IDs are not ownership identifiers. Boundary identity equivalence is a release gate for personal execution.

## Local development identity

Only the `local`/`dev` runtime with development admin simulation, enabled personal connections and an exact nonempty `test:` namespace automatically uses the configured Admin Test User for personal identity. Default REST composition accepts tokenless `/api/me` requests by invoking the configured simulated verifier; caller tokens and forwarded identity headers cannot select another owner. Explicit user-verifier hooks remain token-required and never inherit the admin verifier. Personal MCP adapters require a current authenticated `single_test_user` context before projecting that same configured subject, profile and admin membership claim. Original machine claims are rejected; global MCP/shared/native claims and permissions are unchanged. A different MCP group claim receives no invented membership, and `simulated_admin=false` grants no simulated administrator membership. Production, real-provider, JWT and unauthenticated modes never receive this fallback.

Preserve both `UMBOD_ADMIN_SIMULATED_USER_ID` and `UMBOD_PERSONAL_CONNECTIONS_IDENTITY_NAMESPACE` across restarts to retain ownership; display names and email addresses are not ownership keys. An empty eligible catalogue is legitimate. Publication, an explicit connector-level group grant, owner enablement, provider OAuth consent and explicit discovery remain mandatory; no shared credentials or root-secret generation are introduced.

## Bounded OAuth initiation compatibility

Authorization and refresh providers receive a required immutable callback policy derived per request from trusted settings. Only the local/dev runtime with development admin simulation, enabled personal connections, a valid nonblank `test:` namespace and configured simulated user permits HTTP callbacks to the exact literals `localhost`, `127.0.0.1` or `[::1]`. The default local callback is `http://localhost:18010/api/oauth/downstream-mcp/callback`. Nonlocal, real-provider authentication, production, unauthenticated and otherwise ineligible deployments remain strict. Headers and URI contents never enable this exception. Credentials, alternate loopback spellings, encoded hosts, malformed authorities, invalid ports, controls, Unicode, backslashes, queries and fragments are rejected. Exact callback strings remain bound in encrypted preparation context and grants, without normalization; refresh rechecks the current trusted policy.

Dynamic registration sends the stable display name `Umbod` and declares `application_type=native` only for an already validated local HTTP callback; HTTPS callbacks declare `application_type=web`. An echoed application type must exactly match the request; omission remains compatible with older providers. The client-name echo is not a security binding. Redirect, authentication method, grant, response and scope bindings remain unchanged.

This callback-only exception never changes outbound HTTPS/public-address validation, DNS/rebinding protection, TLS verification, redirect refusal, proxy isolation or retry limits. Resource, issuer, authorization, registration and token destinations remain subject to existing outbound guards.

Explicit true `authorization_response_iss_parameter_supported` keeps the generic callback and requires a nonempty exact response issuer before claiming. Omission or false selects an issuer-bound callback: trusted base plus `/issuer/` and lowercase SHA-256 of the exact validated discovered issuer UTF-8 bytes. Finalize this URI before registration and use it unchanged in registration, authorization, durable context and token exchange. Null and mistyped flags reject initiation. Only the exact matched issuer-bound route may omit the actual response issuer; a supplied empty or mismatching issuer always rejects, including error responses. Route identity comes from canonical raw REST paths, never state, response issuer, host or forwarded headers. Serialized claims verify full state and newly typed bindings before consuming an attempt; providers independently verify the context issuer, route hash and final redirect before token POST. Legacy encrypted prepared records decode as strict generic, without promotion or migration. Those old records retain their opaque adapter context: a nonempty issuer is required before claim, but its exact context comparison remains before token POST rather than before claim. A mismatching legacy callback can therefore consume its old pending attempt without exchanging a token; new generic and issuer-bound records reject mismatches without consumption. Preconfigured clients must externally register the derived URI when support is omitted or false; Umbod does not alter client policy or credentials. State, PKCE, resource, client, policy, expiry, eligibility, one-time claims and replay fences remain unchanged. Failed callback copy directs users back to Connections to check the existing attempt, cancel or wait for expiry before trying again. This compatibility slice is not evidence of a real-provider login.

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
5. `/dashboard` user catalogue and personal MCP actions, plus admin personal-OAuth configuration; reusable owner-scoped API and components remain separate from admin-only state. See [the user dashboard specification](user-dashboard-ui-specification.md).
6. Personal tools use server-level authorization and the verified owner's private discovered inventory, not an administrator-approved per-tool intersection. Administrative/shared discovery credentials must never become user runtime credentials. Newly added tools need explicit rediscovery, not another administrator grant.

## Verification

Run shared store contract tests for both in-memory and persistent adapters, encryption/restart/ownership-tampering checks, stale-write races, missing-principal rejection, and cached capability denial. Re-run API/MCP unit tests, Python lint, shared Semgrep, and disposable Kind running-service verification. Desktop verification is no longer applicable. UI verification applies when the later frontend slice is implemented.

Baseline before implementation: 2,143 API tests and 161 Desktop tests pass; Ruff passes. Shared Semgrep reports 47 existing findings.

First-delivery verification: 2,218 API tests and 161 Desktop tests pass; Ruff passes in both packages. Disposable Kind installation/chart tests and all 23 live runtime tests pass. Shared Semgrep completes with the same 47 findings and no new findings. Review identified a cached template-resource read bypass; ownership-aware resource wrappers and a regression test close it. Personal connection tests cover both storage implementations, cross-owner isolation, encryption, stale writes, competing writes/disconnection, and transactional deletion rollback.
