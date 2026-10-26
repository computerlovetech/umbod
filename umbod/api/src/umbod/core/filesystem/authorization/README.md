# Filesystem authorization

**Responsibility:** Evaluate direct-node permissions through injected identity, namespace, and policy ports. Import the public API from `umbod.core.filesystem.authorization`.

## Files

- `models.py` defines immutable ResolvedIdentity, explicit UnresolvedIdentity, and AuthorizationDecision. A resolved identity requires a USER principal and explicitly supplied GROUP principals, frozen into a frozenset. Principal equality includes type, issuer, and provider ID.
- `ports.py` defines asynchronous FilesystemIdentityResolver.resolve(CallerContext) and FilesystemAuthorization.decide/require contracts.
- `errors.py` defines PermissionDenied for denied require calls.
- `service.py` supplies AuthorizationService with injected resolver, NamespaceDriver, and AccessControlDriver.
- `__init__.py` exposes the public API.

## Evaluation boundary

Unresolved identities, missing nodes, and missing ownership deny. Exact user or trusted group ownership grants every permission on that node. Matching direct user/group grants combine explicitly stored independent permissions; empty grants confer nothing. Recursive grants apply on their own node only. No ancestors are read.

Only missing-node and missing-ownership observations are converted to denial. Resolver and other storage failures propagate. Each decision uses current observations without caching; no atomic check-and-use or mid-stream revocation guarantee is provided. Evaluation neither mutates policy nor reads content.

The resolver is a trust boundary, not an implemented production mapping. Caller observations do not establish canonical principals or trusted group membership by themselves. The separate [browsing service](../browsing/README.md) enforces DISCOVER for complete safe summaries and independently filtered child listing. All custom metadata attributes are DISCOVER-visible. It does not guarantee atomic check/use or mid-operation revocation. Production mappings, inherited/delegated authority, content/mutation authorization services, and REST/MCP enforcement remain deferred. Raw Filesystem and policy stores remain trusted internal capabilities without enforcement.
