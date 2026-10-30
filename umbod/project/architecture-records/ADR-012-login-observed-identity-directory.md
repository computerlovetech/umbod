# ADR-012: Login-Observed Identity Directory

- **Status:** Accepted
- **Scope:** Identity observation, directory persistence, and administrative suggestions

## Decision

An Umbod instance represents one organisation. Its configured authentication provider defines the admission boundary for that organisation. This is not multi-organisation support: issuer validation alone cannot distinguish organisations sharing an issuer.

Maintain a persistent identity directory separate from registered permission groups and authorization state. Observed users are identified by verified issuer and subject and have stable Umbod identifiers. Observed membership values are identified by issuer, configured source claim, and exact value. Equal emails, names, subjects from different issuers, or membership values from different sources never establish identity equivalence.

A dedicated authenticated HTTP operation captures a minimal immutable observation from verified authentication claims. It accepts no client-supplied profile or membership payload. The frontend triggers collection independently of workspace loading. The gateway owns login and token refresh, so browser startup, visible-session resumption, and throttled five-minute visible-session checks observe its current authentication context; this is not an exact token-refresh callback. Other transports may reuse the application operation without introducing a second directory implementation.

Membership observations use the configured MCP permission-group claim, which also supplies REST resource-authorization memberships. The administrator-membership claim is a separate admission policy and must not be substituted when the two settings differ. Profile enrichment may use separately validated identity claims bound to the same issuer and subject; membership values always come from verified access claims. Development simulation does not create verified directory observations.

Directory writes run as best-effort in-process background work. Restart loss is acceptable because subsequent observations are idempotent and can repair missing discovery information. No durable queue or collection guarantee is introduced. Background failures are logged without tokens or profile payloads and do not fail login or workspace loading.

Persist only identity bindings, available display metadata and email verification state, observed membership values, and first/last-seen timestamps. Missing profile claims do not erase known information. Older observations do not replace newer profile information. Duplicate observations are safe under concurrent requests; redundant timestamp writes may be coalesced without dropping new values or changed profiles.

Administrative directory queries are restricted to the currently configured issuer and membership source. A provider change neither merges old identities nor exposes old-provider suggestions through current-provider searches. Observed membership values supplement manual group-ID entry; editing a managed group does not change its identity.

Observation never registers a managed group, modifies its label or description, grants permissions, or proves that an account remains active. Authorization continues to use currently verified claims. The directory is incomplete and may retain historical values. No raw tokens, complete claim payloads, session histories, or historical user-to-group membership relationships are retained.

## Boundaries

The backend owns observation validation, merging, persistence, directory query authorization, and source selection. The frontend owns a nonblocking trigger and suggestion presentation. Store ports and neutral schemas belong to the identity-directory bounded context and use the shared persistence runtime under ADR-001. Request-scoped operations and background operations must not retain request-owned database sessions or mutable request authentication objects.

Existing registered group IDs, grants, and deletion safeguards remain unchanged. The directory does not introduce issuer scoping into legacy permission references by implication. Multi-issuer or multi-organisation permission administration requires an explicit follow-up identity-binding and grant migration decision before it is enabled.

## Consequences

User search and group suggestions become possible without provider-management credentials. Discovery completeness and freshness are explicitly weaker than a provider directory. Profile search is initially administrative; recipient eligibility and ordinary-user search disclosure are separate future features.

## Supporting material

- [ADR-001: Backend-Neutral Persistence Module Boundaries](ADR-001-backend-neutral-persistence.md)
- [ADR-004: One Backend API and a Thin Desktop Boundary](ADR-004-single-backend-api-and-desktop-boundary.md)
- [ADR-011: State Ownership and Rendering Boundaries](ADR-011-state-ownership-and-rendering-boundaries.md)
