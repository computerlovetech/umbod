# ADR-009: Transport-Neutral File Upload Sessions

- **Status:** Accepted
- **Date:** 2026-10-29
- **Scope:** Filesystem upload lifecycle, REST contract, and web client

## Decision

Separate upload coordination from byte transfer. A caller first creates an upload session, transfers raw bytes using the returned instructions, and explicitly completes the upload. The destination file becomes visible only after completion succeeds.

REST exposes session creation through POST on a directory's uploads collection, session inspection through GET on the created session resource, and publication through POST on the session's complete subresource. Creation returns 201 and Location for the session. First publication returns 201 and Location for the file; repeated completion returns 200 and the same file identity.

The session response includes its identifier, expiry, lifecycle status, completion URL, and a discriminated transfer description. The initial transfer type is single: one PUT with a URL, required headers, and explicit authorization instructions. Request bodies declare the name, existing filesystem metadata, and exact nonnegative byte size. Clients do not select object keys, owners, or storage backends.

For existing local and in-memory content adapters, PUT targets the authenticated Umbod session content resource and streams into the existing content driver. Future direct-storage adapters may return an external transfer target without changing session creation and publication semantics. A byte read/write adapter alone does not imply support for issuing direct-transfer instructions.

There is no separate upload-policy endpoint. The server validates permissions and size during creation and transfer. The web client may use an authorized OPTIONS request on the uploads collection to decide whether to offer upload controls. Its successful response uses the standard Allow header; it neither creates a session nor defines a custom HTTP size-limit header.

## State and ownership

Upload records use the application's shared backend-neutral database. Session state is not tied to a worker, REST connection, browser tab, or future MCP session. Persistent database and content deployments support recovery across requests and process restarts; in-memory deployments retain their existing process-lifetime durability.

Sessions bind to the resolved user principal, including issuer, and retain destination, validated metadata, declared size, expiry, staged content, and completion outcome. Unknown and foreign sessions use the existing filesystem's indistinguishable permission-denied behavior.

The initial incomplete-session lifetime is one hour. An expired incomplete session cannot transfer or publish. A completed session remains available for idempotent completion even after that transfer expiry, while its published node still exists. A historical completed session cannot restore a deleted file; completion retries for a removed node return the existing indistinguishable permission-denied response. No automatic completed-session retention purge is introduced in this slice.

Transfer must enforce actual bytes independently of Content-Length and declared size, and the stored content size must match the declaration. Authorization is checked before receiving bytes and again before publishing. Publication also enforces the current configured upload limit; already completed outcomes remain idempotent if limits later change. Interrupted or rejected transfers do not publish a file. A successful transfer stages an immutable content reference; completion publishes that reference without reading the file again. Transitions prevent late or concurrent transfers from changing already published content. Filename availability is checked again during publication; initiation does not reserve names.

Node creation, private caller ownership, content-reference publication, and the completed session outcome share one database transaction. Object storage remains outside that transaction, consistent with ADR-006.

## Client security

The client validates transfer descriptions at the network boundary. Same-origin authorization permits normal Umbod authentication only when the resolved target has the trusted configured API origin. Relative session instructions resolve against that API origin, not necessarily the browser document origin. The transport validates the trusted API origin and configured base path; filesystem adapters supply the expected session identifier, operation path, and method. Unauthenticated external transfers must omit Umbod authorization and cookies. Transfer requests do not follow redirects. Completion instructions must resolve to the expected API session operation before using the authenticated client.

The client must reject unsupported transfer types rather than interpreting them as single uploads. Future multipart transfers require a separate transfer variant, explicit supported-client behavior, part receipts, retry semantics, and cancellation; no placeholder multipart implementation is added now.

## Scope and consequences

The first implementation replaces REST form-data uploads and updates the existing web upload workflow for local and in-memory storage. Downloads are unchanged. S3, other external receiving services, multipart, resumable transfers, and MCP upload tools are deferred.

All application rules remain in core filesystem services, neutral stores remain over the shared database, concrete byte I/O stays in filesystem infrastructure, and REST remains an adapter. Request services retain the existing dependency lifetime boundaries.

Abandoned or superseded immutable content can remain unreferenced, as permitted by ADR-006. Expiry prevents further use but does not reclaim stored bytes or session rows. Admission quotas, physical orphan reclamation, and retention policy need a separate bounded design before claiming automatic cleanup or abuse-resistant storage accounting.

## Alternatives considered

Keeping multipart/form-data uploads would preserve a single request but couple all byte transfers to the REST server. S3 multipart uploads would improve large-file recovery but add part coordination before it is needed. A process-local session dictionary would simplify the first implementation but break shared-worker and persistent-restart behavior. Custom HEAD size-limit headers would introduce a private HTTP convention without removing authoritative validation.

## Supporting material

- [ADR-001: Backend-Neutral Persistence Module Boundaries](ADR-001-backend-neutral-persistence.md)
- [ADR-004: One Backend API and a Thin Desktop Boundary](ADR-004-single-backend-api-and-desktop-boundary.md)
- [ADR-005: One Workspace and Only Usable Controls](ADR-005-unified-workspace-and-usable-controls.md)
- [ADR-006: Filesystem Storage Infrastructure Boundary](ADR-006-filesystem-infrastructure-boundary.md)
