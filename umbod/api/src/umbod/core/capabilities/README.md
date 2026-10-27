# Capabilities

Shared, backend-neutral capability vocabulary and read contracts.

- `domain.py`: full kind-qualified identities and normalized capabilities with input/output schemas.
- `catalog.py`: `CapabilityCatalog`, in-memory identity lookup and missing/conflicting identity errors.
- `cached.py`: `CachedCapabilityCatalog` wrapping a reader with an injected request cache. Its `CapabilityCatalogSnapshot` stores a capability tuple and complete-identity index, not a reader service.
- `availability.py`: publication, activation, readiness and permission policies composed into availability checks.
- `descriptions/`: effective descriptions and description override persistence.
- `tools/`: shared tool schema, naming and output-schema helpers.
- `__init__.py`: lazy public exports.

The cached wrapper loads and indexes the complete catalogue once per successful snapshot, sharing that snapshot between listing and resolution. Duplicate identities reject the load, missing identities preserve `CapabilityNotFoundError`, and failed loads are retryable. Per-wrapper UUID keys isolate separate readers even if they share a typed cache.

Capture and returned capabilities are deep-copied so mutable nested schemas cannot change the retained snapshot. The wrapper is suitable only where listing is the complete lookup universe and a request-local snapshot is acceptable. It does not call the underlying resolver after capture and must not replace fresh invocation or mutation admission.

REST currently opts in only for OpenAPI and downstream MCP assignable-target listing. Native catalogues are already indexed in memory and remain unwrapped. See the [permission boundary index](../../rest/mcp_permissions/README.md) for lifetime and scope.
