# Filesystem Storage Infrastructure Boundary — supporting detail

Preserved from [ADR-006: Filesystem Storage Infrastructure Boundary](../ADR-006-filesystem-infrastructure-boundary.md). These details remain part of the accepted record; relocation does not change their authority or claim that implementation or verification is complete.

## Lifecycle And Behavior

Each composition call creates fresh operation/store objects over the supplied Database. Namespace and policy state is shared through that database; fresh store objects do not reset it. In-memory content is retained only by retaining its adapter instance; local content reopens the configured directory. Hosts retain the concurrency-safe persistence runtime for its intended lifetime, await schema readiness, and construct request-operation services through dependency providers. Filesystem tables join the existing application readiness registry; constructors perform no schema I/O. This ADR does not add services to app.state or wire filesystem REST/MCP operations.

The initial relocation preserved the JSON namespace format. The database amendment deliberately retires it: no implicit import/migration is performed, and existing JSON files are not deleted. SQLite reopening and serialized database transactions replace namespace lock/snapshot behavior. Local content retains immutable keys, publication order, cancellation-safe byte I/O, and POSIX/trusted-directory assumptions.

Namespace nodes, ownership, and grants share the application's neutral persistence database, following ADR-001. Per-node rows replace whole-namespace snapshots. Serialized-write sessions cover root provisioning and mutation validation/publication. Namespace and policy ports remain separate; node creation does not assign ownership. Policy persistence accepts logical node UUIDs independently of namespace existence, with exact principal identity, complete grant replacement, and last-applied owner replacement. Authorization evaluation and combined node/owner transactions remain deferred.

File bytes remain behind ContentDriver. Database transactions do not include local/object-store publication; content must be stored before its reference is published, and unreferenced bytes are not eagerly deleted.

## Permission-safe breadcrumb reads

The REST node breadcrumbs resource returns nonempty items ordered from the highest visible ancestor to the selected node, inclusive. Each item contains only id, name, and kind. The complete flag is true only when the path reaches the discoverable canonical root; the root retains its stored empty name rather than a client-specific label.

The caller must have DISCOVER on the target and every returned ancestor. Missing and inaccessible targets receive the same permission-denied response. Traversal stops at the first missing or inaccessible ancestor and returns the contiguous visible suffix with complete false. It does not skip hidden ancestors, expose their names or identifiers, or report why the path is incomplete. Root access is not required to read an independently accessible descendant.

Hierarchy and policy checks use one existing serialized filesystem transaction. Cycles, non-directory ancestors, malformed root termination, and inconsistent reads after successful authorization fail with sanitized storage errors, not successful partial paths. Breadcrumbs do not read file bytes, change grants, or add MCP tools. This contract does not implement the frontend navigation bar or sibling-folder menus.

## Single-file workspace deletion

Deletion removes one file's namespace entry, ownership, and direct grants in a single serialized database transaction. The application checks the caller's direct-node DISCOVER and DELETE permissions and expected node revision inside that transaction. Parent write access, inherited grants, and administrator status do not grant deletion authority. Directories and the root cannot be deleted through this operation.

REST uses DELETE on the existing node resource with a quoted positive revision in If-Match. Successful deletion returns 204; a stale authorized revision returns 412. A missing conditional header returns 428, and unsupported conditional forms return validation errors. Authorized OPTIONS exposes deletion eligibility without reserving permission or bypassing the mutation's checks. Missing and inaccessible nodes remain indistinguishable.

Removal is permanent from the workspace, with no trash or restore workflow. It does not call ContentDriver or promise immediate physical erasure. Retained upload-session history cannot restore a removed file; retrying completion must not report a deleted node as successfully published. Physical orphan reclamation and session retention remain separate concerns.

## Root group policy administration contract

The root-access management API accepts only expected_revision and groups; each group contains an exact group_id and nonempty permissions. Responses contain only status, revision, groups, and blocked_group_ids. The request-scoped backend selects the local development issuer only when local authentication is enabled, otherwise the exact configured OIDC issuer. Missing or blank issuer configuration fails closed with filesystem_policy_unavailable; issuer and claim configuration are not client policy fields.

Inspection projects valid nonrecursive groups for that issuer only. Saves replace only that editable scope, including when groups is empty. Foreign-issuer, user/system, recursive, and malformed grants remain unchanged. Nonblank current-issuer group IDs with preserved recursive or malformed grants are blocked from assignment and excluded from editable projection. Revisions cover the original root policy state and all grants plus the exact managed issuer, so authority changes invalidate stale saves. Existing serialized transaction ports provide atomic conflict checks and reconciliation without a persistence migration. This scoped contract does not assert a new architecture decision.

## Direct-node group sharing

[ADR-013](../ADR-013-direct-node-group-sharing.md) defines authorized group-only inspection and replacement, registered-recipient validation, protected grant preservation, and opaque access-policy preconditions. It extends the application boundary without changing direct-node authorization, content revisions, or raw store compatibility.

## Enforcement

- Keep the exact infrastructure source-package allowlist: persistence and filesystem, plus the root package.
- Keep an exact public infrastructure export allowlist containing approved runtime/composition/configuration symbols only.
- Keep the prohibition against core importing infrastructure and against external deep infrastructure imports.
- Prohibit concrete filesystem driver exports at the infrastructure root.
- Assert absence of old core adapter/configuration locations and host filesystem imports in neutral filesystem modules.
- Use fresh-process import checks for core isolation and lazy infrastructure driver loading.
- Run shared namespace/policy contracts against both existing database drivers; preserve independent content adapter coverage.
- Verify SQLite reopening, concurrent transactions, and process-safe namespace mutation; retire JSON-specific tests rather than preserving dead implementations.
- Keep neutral store behavior tests at public protocol boundaries. Retain concrete driver/content-specific checks under approved infrastructure test boundaries.
