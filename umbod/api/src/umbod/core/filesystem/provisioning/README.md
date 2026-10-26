# Trusted root provisioning

- `models.py` defines required immutable RootBootstrapSpec and RootBootstrapGrant. Principals are USER/GROUP only with nonblank issuer and ID preserved exactly, unique per spec; permissions are immutable and explicitly supplied. Zero grants are valid. Grants are always nonrecursive and root-direct.
- `ports.py` defines RootProvisioning.provision.
- `service.py` supplies RootProvisioningService using FilesystemTransactions.
- `__init__.py` exposes these contracts.

This explicit trusted capability atomically initializes a clean unowned root, assigns SYSTEM_ROOT_OWNER (SYSTEM, issuer `umbod:system`, ID `filesystem-root`) and adds only the supplied grants. Group membership alone conveys no authority. There is no first-caller ownership, startup invocation or system-user bypass.

Canonical system ownership is the reserved trusted completion signal, not authority to adopt arbitrary legacy roots. SYSTEM was not previously representable. No schema/marker table is needed. An unowned root with children or orphan root grants, or a root with any different owner, raises ProvisioningConflict without mutation. No automatic migration is attempted.

**Bootstrap is not reconciliation.** On already-canonical system ownership, provision returns the root summary without changing any grants: revoked grants stay revoked, newly supplied grants are not added, changed permissions are ignored, existing grants are not removed. A changed bootstrap configuration does not update access. The summary does not report an access configuration update.

Raw namespace behavior remains lazy and unowned. Trusted raw namespace/policy capabilities can mutate anything, including the completion signal, and must not be exposed as authorization-safe APIs. The optional operator CLI `umbod filesystem bootstrap` invokes this capability with a required trusted policy file. REST/MCP ordinary browsing and creation never invoke provisioning. The separately authenticated admin root-access editor initializes clean roots without CLI use and repeatedly reconciles direct root GROUP grants through administration transactions, not this one-time bootstrap operation. Existing USER and recursive GROUP grants remain outside that editor's scope.
