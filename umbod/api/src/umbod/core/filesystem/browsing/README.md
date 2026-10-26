# Authorized filesystem browsing

**Responsibility:** Caller-aware, read-only root discovery, direct lookup, and child listing. Import FilesystemBrowsing, NodeSummary, and BrowsingService from `umbod.core.filesystem.browsing`. This opt-in service does not change the trusted raw Filesystem API or add transport wiring.

## Files

- `models.py` defines frozen NodeSummary with required explicit fields and forbidden extra fields.
- `ports.py` defines FilesystemBrowsing.get_root(caller), get_node(caller, node_id), and list_children(caller, parent_id).
- `service.py` implements the port with injected NamespaceDriver and FilesystemAuthorization only.
- `__init__.py` exposes the public API.

## Visibility policy

DISCOVER alone authorizes the complete summary: id, parent_id, name, kind, metadata, created_at, updated_at, and revision. All custom metadata attributes and the metadata content type are DISCOVER-visible, not separately protected. Do not store secrets in metadata expecting READ to protect them. READ alone does not confer DISCOVER. Summaries use an explicit field allowlist: no content reference, storage key, or byte size. Existing RootParent represents the root parent. Each summary deep-copies metadata, including mutable attributes, so modifying it cannot affect namespace state or another summary.

Root discovery requires DISCOVER on the root returned by the namespace. Direct lookup requires only the target's DISCOVER; no ancestor checks or reads are added. Listing requires parent DISCOVER before reading its kind: an accessible file raises WrongNodeKind, while an inaccessible file raises PermissionDenied. Each immediate child independently requires DISCOVER; denied children are omitted, with no hidden counts. Filtering retains the namespace's exact case-sensitive Unicode name order, without normalization. Empty and fully filtered directories both yield an empty sequence.

Missing and inaccessible targets raise PermissionDenied with the normal evaluator's identical `discover denied for node {node_id}` text. Namespace MissingNode after successful authorization, including a vanished listing parent, becomes the same denial; root namespace absence uses the existing root ID. Target authorization denials from injected implementations are normalized to this same message with suppressed exception context; their internal denial details are not exposed. Timing side-channel equivalence is not promised. Only child PermissionDenied is omitted. Resolver, authorization, and other namespace/storage failures propagate and abort the whole operation. Results are fully materialized before return; no partial sequence is exposed on failure.

Every operation re-evaluates authorization; there is no cache. Authorization and namespace reads are separate observations: no atomic check/use, consistent snapshot, or mid-operation revocation guarantee is provided. The existing namespace's lazy root initialization remains accepted. Browsing adds no writes, content dependency, identity mapping, inheritance, configuration, schema, or REST/MCP surface.

## Verification

Public-port acceptance runs against existing in-memory and SQLite namespace/policy fixtures with the real evaluator and test-only identity resolver. Contract tests inject port faults and verify safe projections, independent filtering, race denial, failure propagation, and absence of content, mutation, or ancestor calls. The feature record is `.atdd/features/filesystem/12-authorized-browsing.md`; this tracked index is authoritative for the implemented policy.
