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

## Sharing-recipient name search and principal resolution

Verified authenticated users admitted by the currently configured issuer may discover observed users through the node-authorized sharing interface without administrator membership. This supersedes the initial standalone MCP user-search policy: `filesystem_search_sharing_recipients` requires current direct-node DISCOVER and SHARE authority before consulting the directory. There is no independent `search_users` MCP tool or alias. Administrative REST directory search retains its separate broader diagnostic contract.

Sharing discovery accepts one required nonblank query of at most 200 characters and optionally selects group or user recipients. Matching observed users remains a case-insensitive literal substring of the observed name after whitespace normalization, supporting first, last, and contiguous full names without parsing names into separate fields. Emails and subjects are not search inputs or fallback names; blank queries do not enumerate the directory. The combined sharing response contains at most 50 eligible recipients and indicates when additional matches exist.

User results disclose only the user recipient type, stable Umbod user identifier, and observed name as a display label. Duplicate names remain distinct by identifier; absent names are not searchable. Issuer, subject, email, verification state, membership observations, and timestamps remain outside this projection. The neutral directory search accepts application-selected subject exclusions and applies them before result truncation, allowing sharing to omit protected principal collisions without per-result identity lookups or a second directory implementation.

A core lookup resolves a selected stable user identifier only within the configured issuer. Missing and foreign-issuer identifiers are indistinguishable. The filesystem authorization adapter maps the stored binding to its existing USER principal using exact issuer and subject, never the directory identifier, display name, or email as the authorization identifier. Search and resolution perform no permission writes, confer no authority, and establish neither recipient eligibility nor account activity. [ADR-015](ADR-015-direct-node-user-sharing.md) extends the existing sharing operations and recipient projections with user targets, including filtered REST views and explicitly scoped replacement.

MCP constructs sharing operations per invocation using the shared persistence runtime and captures current verified caller identity. Tool listing does not read the identity directory. Recipient search reuses the sharing transaction's session-bound directory reader after node authorization; no nested read session is opened. The store searches and resolves within the configured issuer using existing neutral storage without introducing a second directory or provider-management integration.

## Consequences

Sharing-recipient search and administrative group suggestions remain possible without provider-management credentials. Discovery completeness and freshness are explicitly weaker than a provider directory. Sharing discovery, eligibility, and individual file permissions follow the authority and mutation boundary in ADR-015; search itself grants no access.

## Supporting material

- [ADR-001: Backend-Neutral Persistence Module Boundaries](ADR-001-backend-neutral-persistence.md)
- [ADR-004: One Backend API and a Thin Desktop Boundary](ADR-004-single-backend-api-and-desktop-boundary.md)
- [ADR-011: State Ownership and Rendering Boundaries](ADR-011-state-ownership-and-rendering-boundaries.md)
