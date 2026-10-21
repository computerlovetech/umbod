# Personal connections

Principal-scoped enablement and opaque authorization state, independent of shared credentials and runtime execution.

- `models.py`: canonical ownership keys, explicit authorization states, lifecycle transitions and revision conflicts.
- `ports.py`: validated principal provider and personal connection storage contracts.
- `principal.py`: pure verified-claims mapping and `VerifiedClaimsPrincipalProvider`, exported through this package. Identity policy maps Google/Auth0 subjects and tenant-scoped Entra object IDs under the configured namespace, rejecting mismatched and machine identities. Token verification stays in REST/MCP.
- `service.py`: owner-bound operations; missing validated identity is rejected before storage access.
- `inmemory.py`: serialized in-memory storage adapter.
- `inventory_models.py` and `inventory_ports.py`: validated catalogue queries, enablement commands, secret-free projections and public selection port.
- `inventory.py`: published personal-definition and connector-grant eligibility, effective descriptions, explicit opt-in and owner cleanup after withdrawal.
- `oauth_models.py` and `oauth_ports.py`: validated durable attempt, callback-claim and resumable provider contracts.
- `oauth_service.py`: request-scoped initiation, owner-bound status/cancellation and worker-independent callback completion.
- `__init__.py`: public lifecycle and inventory domain API.

Missing records are disabled and unauthorized. Enabling creates an unauthorized record; disabling retains authorization; disconnect disables and clears it. Meaningful changes generate opaque revisions. Disconnect always invalidates an existing revision, including when already disabled and unauthorized, to reject pending authorization writes; repeated requests preserve disabled/unauthorized state. Conditional authorization replacement cannot create records or overwrite stale revisions. Persistent storage is implemented by `../stores/personal_connections.py`. The production factory uses its definition-bound adapter, checking target existence and personal ownership inside each serialized mutation transaction so concurrent deletion cannot leave orphaned state. The detached adapter remains available for standalone lifecycle contracts.

Personal authorization availability defaults on when the deployment identity policy, persistent SQLite and encryption are configured; explicit opt-out remains available. This does not automatically enable any user's connector or grant downstream consent. Reserve preparation before outbound registration and publish only after encrypted provider context is durable. Callback claims and token installation are serialized; completion checks the current connection revision, definition, publication and connector grants. Terminal attempts erase sensitive preparation context. Failure/cancellation preserves existing authorization; runtime execution remains disabled. Persistence lives under `../stores/personal_oauth_attempts.py`, with transactional deletion cleanup. Provider I/O lives under `../adapters/personal_oauth/`, independently of the shared SDK coroutine workflow.
