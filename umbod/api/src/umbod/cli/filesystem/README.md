# Filesystem operator commands

`umbod filesystem bootstrap --policy-file PATH` explicitly initializes system root ownership and supplied direct grants in the configured persistence database. The required JSON policy contains `grants`; each grant has a USER/GROUP `principal` with exact `type`, `issuer` and `id`, and an explicit `permissions` collection. Core validation rejects blank identities, duplicate principals, recursive flags and unknown fields. `/dev/stdin` is supported for trusted deployment tooling.

## Modules

- `command.py` registers the CLI boundary, validates input before configuration/runtime creation, and emits fixed sanitized status messages.
- `ports.py` defines the bootstrap policy source interface.
- `policy.py` reads and validates the operator-supplied policy file.
- `service.py` opens the configured prepared persistence runtime, invokes the shared core provisioning port and guarantees shutdown.
- `__init__.py` exposes command registration.

This is a trusted operator capability, not a user or MCP administration endpoint. It never selects the first caller as owner. Conflicting or dirty legacy roots require explicit recovery or migration rather than automatic adoption. Completed system ownership causes a no-op: changing the policy file does not add, remove or restore grants. No ordinary request or application startup invokes this command.
