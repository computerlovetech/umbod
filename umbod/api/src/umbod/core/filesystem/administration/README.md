# Root group policy administration

- `ports.py` defines RootGroupPolicyManagement.inspect/save and narrow read/write transaction and session ports.
- `models.py` defines immutable explicit group policies, save commands, observed state and views. Nonblank issuer/group keys remain exact; permissions have no implications or defaults. Empty submitted groups explicitly initialize or revoke root group access.
- `service.py` classifies clean uninitialized, canonical system-owned ready, and conflicting legacy states. It fingerprints canonical root state and all root grants before serialized optimistic reconciliation.
- `errors.py` distinguishes stale revisions from legacy or recursive-scope conflicts.
- `__init__.py` exports these public contracts.

Inspect never initializes namespace or ownership. Save validates the expected revision and scope before any initialization. A clean root is initialized with SYSTEM_ROOT_OWNER atomically with submitted grants; dirty or differently owned roots are never adopted. The editor replaces all direct nonrecursive root GROUP grants, including grants originally created through the optional CLI. Omitted direct groups and empty direct policies are removed. USER grants, recursive GROUP grants, ownership, children and child policies are preserved. Submitting an existing recursive group's exact issuer/ID conflicts.

Revisions detect external raw root policy changes and concurrent saves, but ordinary children added to a configured root do not invalidate edits. Unrelated orphan UUID policies do not participate. Session exceptions and cancellation roll back the complete save.

This is trusted configuration, not ordinary filesystem authority. Configuring a future issuer does not verify a user. Core has no transport, authentication middleware, configuration or infrastructure imports. REST supplies admin authorization and configuration hints; ordinary browsing and creation still require upstream-verified identities. The CLI remains optional one-time bootstrap and never reconciles a completed root.
