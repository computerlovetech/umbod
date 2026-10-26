# Filesystem authorization

**Responsibility:** Evaluate direct-node permissions through injected identity, namespace, and policy ports. Import the public API from `umbod.core.filesystem.authorization`.

## Files

- `models.py` defines immutable ResolvedIdentity, explicit UnresolvedIdentity, and AuthorizationDecision. A resolved identity requires a USER principal and explicitly supplied GROUP principals, frozen into a frozenset. Principal equality includes type, issuer, and provider ID.
- `ports.py` defines asynchronous FilesystemIdentityResolver.resolve(CallerSnapshot) and FilesystemAuthorization.decide/require contracts.
- `errors.py` defines PermissionDenied for denied require calls.
- `service.py` supplies AuthorizationService with injected resolver, NamespaceDriver, and AccessControlDriver. Its shared `allows_resolved` evaluator is also used by creation inside a serialized transaction; policy is not duplicated.
- `resolver.py` supplies VerifiedIdentityResolver: only UPSTREAM_VERIFIED with SubjectIdentity, nonblank DeclaredIssuer and subject resolves. Exact unmodified issuer/subject becomes USER; observed groups become deduplicated immutable GROUP principals in that same issuer namespace. A blank group rejects the entire snapshot. No normalization, directory lookup, provider fallback or cache is used. Other provenances and unavailable identity observations are unresolved.
- `local_resolver.py` supplies explicit opt-in LocalDevelopmentIdentityResolver configured with a nonblank expected USER principal. It delegates genuine UPSTREAM_VERIFIED snapshots to unchanged VerifiedIdentityResolver and additionally accepts only LOCAL_SIMULATION with exactly matching issuer/subject and valid nonblank group IDs. Groups retain the expected issuer namespace. Resolution changes no grants, ownership or authorization decisions; production and MCP composition remain strict.
- `__init__.py` exposes the public API.

## Evaluation boundary

Unresolved identities, missing nodes, and missing ownership deny. Exact user or trusted group ownership grants every permission on that node. Matching direct user/group grants combine explicitly stored independent permissions; empty grants confer nothing. Recursive grants apply on their own node only. No ancestors are read.

Only missing-node and missing-ownership observations are converted to denial. Resolver and other storage failures propagate. Each decision uses current observations without caching; no atomic check-and-use or mid-stream revocation guarantee is provided. Evaluation neither mutates policy nor reads content.

The resolver is a trust boundary with an explicit verified-observation mapping. REST and MCP capture authenticated snapshots and delegate decisions to this module. SYSTEM principals cannot enter ResolvedIdentity; verified strings equal to the internal root owner still map to USER, never SYSTEM. There is no system-user resolver or bypass. Caller observations do not establish canonical principals or trusted group membership by themselves. The separate [browsing service](../browsing/README.md) enforces DISCOVER for complete safe summaries and independently filtered child listing. All custom metadata attributes are DISCOVER-visible. It does not guarantee atomic check/use or mid-operation revocation. Inherited/delegated authority, authorized content access and remaining mutation services remain deferred; delivery adapters enforce browsing and empty creation through the shared core operation ports. The separate [creation service](../creation/README.md) resolves once and authorizes parent DISCOVER then WRITE using this same evaluator inside its node/owner transaction. Raw Filesystem and policy stores remain trusted internal capabilities without enforcement.
