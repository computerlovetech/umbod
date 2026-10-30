# ADR-013: Direct-Node Group Sharing

- **Status:** Accepted
- **Scope:** Filesystem sharing application operations and HTTP access-policy resources

## Decision

Implement group-only direct-node sharing in the filesystem core, exposed through the existing node access resources. The initial slice contains policy inspection and complete replacement of an explicitly editable group scope. It does not add a sharing dialog, user-sharing inputs, inherited access, ownership transfer, or provider identity remapping.

Both inspection and replacement require the caller's existing direct-node DISCOVER and SHARE authority. Administrator status alone is not authority over a node. Missing and inaccessible targets remain indistinguishable. Authentication resolution precedes a serialized transaction; authorization, policy observation, revision comparison, managed-group validation, and mutation use the same transaction and current persisted state. SHARE permits node policy management without changing ownership or implying authority over descendants.

## Recipient and mutation boundaries

Recipients must be registered managed Umbod groups. Login observations are not recipients or authorization evidence. The backend selects the exact configured issuer, with the existing explicit local-development issuer selection in local authentication mode. Issuer, recursion, ownership, and arbitrary principal types are not client policy inputs.

A narrow sharing transaction port provides namespace, access-policy, and registered-group collaborators bound to one existing persistence database session. Group validation occurs inside the serialized write transaction shared with group lifecycle operations. Sharing writes do not implicitly register recipients. If sharing commits first, existing group deletion safeguards reject deletion while referenced; if deletion commits first, sharing rejects the missing recipient without recreating it.

Only valid, registered, nonrecursive group grants for the managed issuer are editable. Replacement, including an empty group list, changes only that scope. Foreign-issuer, user/system, recursive, malformed, and unregistered grants remain protected. Protected grants with the same group principal block assignment because the grant persistence key does not distinguish recursion. Validate the complete replacement before removing or upserting grants; failure rolls back the operation.

Existing raw access-control APIs retain their current behavior. The new application operation uses a non-registering write path and does not change ownership, clear all node policy, publish content, or increment the content revision to represent sharing changes. Root policy administration retains its existing contract.

## Additive sharing

The core sharing service also supports an additive single-group operation. It requires current direct-node DISCOVER and SHARE authority and a registered, unblocked recipient, using the same managed-issuer and protected-scope rules as inspection and replacement. It unions explicitly requested permissions with the recipient's existing manageable grant inside one serialized sharing transaction. It never removes access, changes other grants, registers recipients, transfers ownership, increments node content revisions, or implies descendant access.

The operation returns the exact group ID, node ID, authoritative permission union, and whether it changed persisted access. An identical or subset request performs no write and returns `changed: false`, but still validates current authority and recipient eligibility. Nonempty permissions are explicit inputs; sharing adds no implicit permission. No expected policy revision is required because the union is computed against current state in the transaction, not through an inspect-and-replace retry. A later explicit replacement retains its existing complete-scope semantics.

MCP exposes `filesystem_list_sharing_groups` over the existing node-authorized recipient query and `filesystem_share` over this additive operation. Tool inputs cannot select issuer, owner, caller, recursion, or arbitrary principal types. Discovery remains free of sharing-service construction and policy reads; verified invocation identity and authoritative core checks apply to each call. Both tools use the existing observed registration and sanitized error boundary. The sharing tool is a non-destructive, idempotent mutation, not a policy replacement or revocation interface.

## Concurrency contract

Node content revision is not an access-policy revision. Sharing uses a canonical opaque revision covering node identity and revision, ownership, the managed issuer, and all grants, including protected grants. Registered-group eligibility affecting an existing grant's editability also participates in the revision, preventing catalogue changes from silently altering replacement scope.

Inspect and successful replace return the authoritative group projection, blocked group IDs, and revision. HTTP responses expose the quoted revision as an ETag. PUT accepts only groups in its body and requires a strong opaque If-Match tag. Missing, malformed, and stale preconditions produce 428, 422, and 412 respectively. Authorization occurs before policy comparison and recipient validation; transport shape validation does not expose node state.

## Access semantics

Grants authorize only their target node. Sharing a directory does not share its children. Direct file access does not require access to its ancestors. Sharing inspection does not disclose ownership, foreign principals, protected grant contents, or provider directory records through the editable projection.

## Batched sharing summaries

The existing core sharing service exposes transport-neutral batch summaries for node listings. Each requested node independently requires direct-node DISCOVER and SHARE authority. Missing and inaccessible nodes return the same restricted summary, with `can_share: false` and no grants field. Unresolved callers remain unauthorized; persistence failures and cancellation are not converted into restricted results.

Authorized summaries contain `can_share: true` and manageable direct grants, using the same protected-scope selection rules as policy inspection and replacement. Recipient metadata uses an explicit recipient type, exact identifier, and current display label. Initially only group recipients are supported; generic summary structure does not enable user sharing. Empty grants describe an empty manageable scope, not the absence of every form of access.

A batch resolves identity once and observes authorization, policy, and labels through one existing sharing transaction. Registered-group metadata is read once only when a node is authorized. Duplicate node IDs are returned once in first-request order. An empty request validates identity but does not open a transaction. Summaries disclose neither protected policy contents, issuer, ownership, nor policy revisions. REST and MCP adapters reuse this operation rather than implementing their own authorization or grant selection.

MCP browsing enriches only returned target nodes and entries through one batch summary query per invocation. Modern ls, tree, and stat and the existing root, node, and child-list reads use the same adapter projection. Nested sharing metadata contains authority and manageable grants without repeating the node identifier. Breadcrumbs and creation, upload, content-read, and deletion responses retain their existing contracts. Readable output and advertised schemas describe the same restricted and authorized states.

Browsing and sharing observation are separate transactions; metadata is current at sharing observation, not an atomic snapshot of the earlier listing or a promise of future authority. Shared discovery constructs no caller-specific sharing service or persisted policy query. Managed-issuer selection is shared configuration used by REST and MCP composition, while MCP identity resolution remains verified-only.

## Workspace follow-up

The Files workspace composes a group-sharing dialog using its existing outline-icon, dialog, and form conventions. Sharing actions remain hidden until node-specific DISCOVER and SHARE authority is confirmed. Eligibility is not inferred from administrator status, file visibility, or another operation's permission.

A node-authorized eligible-groups query exposes registered group IDs, labels, and descriptions for selection without granting administration access or revealing login observations. It uses the same sharing transaction and authorization boundary, excludes protected principal collisions, and does not weaken replacement-time validation. Group metadata changes do not change access-policy revisions.

The dialog edits only the complete editable group scope. It preserves exact IDs, untouched permissions, and direct-node scope, and reconciles successful authoritative responses without reloading the workspace. Conflicts preserve the draft until an explicit reload and review; uncertain mutation outcomes require authoritative reconciliation before another save. Navigation and disposal fence obsolete asynchronous results, and pending writes prevent duplicate submission and dismissal.

## Verification

Behavior contracts cover both persistence drivers, independent SQLite connections, stale replacements, both sharing/deletion orderings, invalid-recipient rollback, protected-scope preservation, blocked principal collisions, issuer and ownership changes, revocation, and non-inherited access. HTTP tests verify request eligibility, strict group-only bodies, opaque preconditions, sanitized errors, authoritative responses, and unchanged remaining planned resources. Kind verification exercises authenticated running services without introducing fixture data into production images or chart values.

## Supporting material

- [ADR-001: Backend-Neutral Persistence Module Boundaries](ADR-001-backend-neutral-persistence.md)
- [ADR-004: One Backend API and a Thin Desktop Boundary](ADR-004-single-backend-api-and-desktop-boundary.md)
- [ADR-006: Filesystem Storage Infrastructure Boundary](ADR-006-filesystem-infrastructure-boundary.md)
- [ADR-012: Login-Observed Identity Directory](ADR-012-login-observed-identity-directory.md)
