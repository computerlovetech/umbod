# ADR-015: Shared Group and User Sharing Targets

- **Status:** Accepted
- **Scope:** Extending existing filesystem sharing operations and recipient projections

## Decision

Extend the existing filesystem sharing operation and recipient domain model to support users alongside groups. There is one additive sharing operation and one MCP mutation tool, `filesystem_share`. Do not introduce recipient-type-specific sharing, grant-inspection, or revocation tools.

A sharing command identifies its recipient with a discriminated group or user target and explicitly requests a nonempty permission set. Group targets use their exact managed group identifier. User targets use the stable opaque identifier returned by `filesystem_search_sharing_recipients`. The configured issuer is selected by the backend, never by the client. Existing issuer-qualified USER and GROUP principals and shared access-grant persistence remain the authorization representation.

## Authorization and identity binding

Every sharing invocation requires current direct-node DISCOVER and SHARE authority. Administrator status alone is insufficient. Authentication resolution precedes the serialized sharing transaction; node authorization, recipient binding, protected-scope validation, and mutation observe the same persistence session and current state. Missing and inaccessible nodes remain indistinguishable, and node authorization precedes recipient lookup.

Groups must already be registered. Users must resolve to an observed identity under the configured issuer. A selected user identifier resolves to the exact stored issuer and subject; names, emails, and opaque directory identifiers are never authorization principal identifiers. Unknown and foreign-issuer user selections have the same invalid-recipient outcome. A recorded verified identity establishes selection eligibility for this slice, not proof that an account remains active.

The directory owns a session-bound neutral lookup and reverse-profile reader. Standalone directory operations open a read session and delegate to that reader. Sharing composes it with the existing transaction session; it must not open a nested database session while holding the serialized writer boundary. No new permission schema, identity store, database runtime, or provider-management integration is introduced.

## Additive policy semantics

The shared operation unions requested permissions with the selected recipient's manageable direct grant. Identical or subset requests return unchanged without a policy write but still validate current authority and recipient eligibility. No permission, including DISCOVER, is implicit. Normal reading requires explicit discover and read permissions.

Only nonrecursive, nonempty valid grants for eligible recipients under the managed issuer are editable. A protected grant colliding with the same principal blocks assignment. Foreign-issuer, recursive, malformed, system, and unresolved-user grants remain protected. All validation precedes mutation.

Sharing never transfers ownership, modifies content, increments content revisions, alters another principal, implicitly registers recipients, or grants descendant access. Sharing a directory does not share its children; direct file access does not require ancestor access. Concurrent additions union against current state within the serialized transaction.

## Existing MCP tool and compatibility

`filesystem_share` accepts the canonical recipient-based command for both groups and users. Its canonical result identifies the node, recipient target, authoritative permission union, and changed status. Existing group-only requests using the top-level group identifier remain accepted at the MCP boundary and retain their original response shape. Ambiguous mixtures of canonical and legacy fields are rejected, and advertised input/output schemas describe both accepted contracts. Both forms normalize into the same core command and operation.

`filesystem_search_sharing_recipients` is the single MCP sharing-recipient discovery tool. It replaces `filesystem_list_sharing_groups` and `search_users`; neither old name remains as an alias. There are no `filesystem_share_user`, `filesystem_revoke_user`, or `filesystem_list_user_shares` tools. A general revocation tool is outside this correction rather than being introduced as a user-only exception.

Sharing remains observed, additive, idempotent, and non-destructive at the MCP boundary. Fresh caller capture and authoritative execution checks apply to every invocation. Tools remain root tools, not connector-scoped tools. Discovery constructs no caller-specific application service and performs no directory or policy reads.

## Node-authorized recipient discovery

Recipient search belongs to the filesystem sharing application port, not an MCP adapter that joins independent directories. Its required node identifier establishes the current DISCOVER and SHARE authority boundary before any registry or directory discovery. Missing and inaccessible nodes remain indistinguishable. Search observes eligibility and directory data in the existing serialized sharing transaction and performs no writes.

The tool accepts a required nonblank query of at most 200 characters and an optional `recipient_type` selecting group or user recipients. Omission selects both. Explicit nulls, unknown fields, client-selected limits, issuer, subject, owner, and recursion are invalid input. The core receives validated search text and an explicit existing sharing scope rather than an optional internal state.

Groups are drawn from the same registered-group and protected-collision selection used by REST eligible-group discovery. Search matches literal substrings of exact group identifiers or display labels after case and whitespace normalization. Users come from the configured-issuer observed-name search, preserving its verified-caller requirement and name-only matching. A user or combined search fails closed if directory authority is missing; a group-only search does not access the user directory.

Protected same-principal user collisions are excluded before the directory applies its result limit. The shared manageable-grant predicate determines these exclusions; the neutral directory query carries only excluded subjects, not filesystem rules. This prevents blocked matches from hiding otherwise eligible users and avoids per-result resolution queries, backfill loops, or nested sessions.

Results reuse the existing typed labelled sharing-recipient projection. They expose only recipient type, exact group identifier or opaque user identifier, and display label. Passing type and identifier to `filesystem_share` requires no further identity lookup by the client; labels remain display metadata and are not accepted as mutation authority. Duplicate labels remain distinct identities.

The response contains at most 50 eligible recipients, deterministically ordered by type, normalized label, and typed identifier, with groups before users. `has_more` reports additional eligible matches beyond that limit. There is no client-selected limit, cursor, or offset in this slice; callers narrow the query or filter a recipient type. Search and returned eligibility grant no access; sharing revalidates current authority, binding, and protection rules on every mutation.

## Unified sharing summaries

Extend the existing sharing-recipient projection with a discriminated user recipient alongside the existing group recipient. Group recipients retain their exact identifier and label shape. User recipients expose only their opaque user identifier and current observed name as a label. Issuer, subject, email, ownership, and protected grant contents are not disclosed.

The existing batch sharing summary returns manageable group and user grants under its current node-specific DISCOVER and SHARE gate. Restricted nodes still return `can_share: false` without grants. Empty grants describe an empty manageable scope, not the absence of every form of access. Batch directory profile reads reuse the same transaction and are not repeated for each listed node. Only verified users under the configured issuer can receive user-directory projections; existing explicitly configured local group behavior does not become directory authority.

MCP browsing consumes this shared projection for root, node, children, ls, tree, and stat responses. No parallel user-grant inspection projection is retained.

## Unified REST policy resources

Generalize the existing node access resource and its core inspection and replacement operations rather than retaining a group-only policy interface or adding per-user resources. The access view contains typed labelled grants, typed blocked recipient targets, and an opaque whole-policy revision. It does not expose protected grant permissions, issuer, subject, or ownership. Inspection and batched summaries share recipient projection and protection rules.

GET accepts an optional `recipient_type` query selecting group or user recipients; omission selects both. Filtering changes the returned projection, not the underlying policy or revision scope. PUT requires an explicit group or user `recipient_type` query and a strict grants body containing unlabelled targets and explicit permissions. Every target must match the selected type, and typed identities must be unique. Missing, invalid, empty, or repeated mutation scopes are rejected rather than interpreted as a whole-policy replacement.

Revisioned replacement, including an empty grants list, changes only manageable direct grants of the selected type. It preserves the other type and all protected or unresolved grants. Resolve and validate every submitted recipient and protected collision before removing any grant. User-scoped replacement requires verified configured-issuer directory authority even when clearing an empty selection. It reuses the existing serialized sharing transaction, exact user binding, grant writer, and permission evaluator.

The revision covers the whole policy independent of the read filter. User changes invalidate older group views, and group changes invalidate older user views. Recipient binding or eligibility changes affecting replacement scope also invalidate stale observations; display-label changes alone do not. Existing strong If-Match validation, 428/422/412 outcomes, authority-before-observation safeguards, sanitized errors, and no-store responses remain intact.

The frontend migrates to the unified wire shape in the same change. Existing group-only sharing dialogs and eligibility probes explicitly request the group filter and save with the group replacement scope. They retain complete group-draft editing, conflict review, uncertain-outcome recovery, and pending-operation guards. The eligible-groups discovery resource and trusted root administration remain explicitly group-specific. The old groups-only node access body is removed; it is not silently reinterpreted as an unfiltered replacement.

A combined sharing UI, shared-file discovery, file-reference delivery, notifications, per-recipient revocation tools, inherited access, and ownership transfer remain separate work.

## Verification

Behavior contracts cover both target types through the same public operations, exact identity mapping, authority before lookup, protected collisions, additive retries, concurrent unions, unchanged content and ownership, mixed summaries, filtered views, global revisions, and symmetric replacement-scope preservation. MCP tests retain canonical group/user targets, legacy group compatibility, ambiguous-input rejection, root-only exposure, minimal authoritative output, and sanitized failures. REST tests cover required mutation scope, strict bodies, filtered and mixed views, preconditions, and sanitized errors. Frontend tests verify explicit group query selection and that saving a group draft preserves stored user grants. Recipient-search contracts additionally verify both filters and omission, readonly behavior, authority before discovery, protected-recipient exclusion before truncation, typed identity collisions, and absence of the retired tools. Kind exercises unified recipient discovery, both targets through `filesystem_share`, mixed metadata, filtered REST views, replacement and revocation for both types, cross-type revision conflicts, and surviving recipient access.

## Supporting material

- [ADR-001: Backend-Neutral Persistence Module Boundaries](ADR-001-backend-neutral-persistence.md)
- [ADR-004: One Backend API and a Thin Desktop Boundary](ADR-004-single-backend-api-and-desktop-boundary.md)
- [ADR-006: Filesystem Storage Infrastructure Boundary](ADR-006-filesystem-infrastructure-boundary.md)
- [ADR-008: Event-Synchronized In-Memory Tool Runtime](ADR-008-event-synchronized-tool-runtime.md)
- [ADR-012: Login-Observed Identity Directory](ADR-012-login-observed-identity-directory.md)
- [ADR-013: Direct-Node Group Sharing](ADR-013-direct-node-group-sharing.md)
