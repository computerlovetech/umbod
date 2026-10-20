# Desktop backward compatibility only

This package exists exclusively to repair or import historical desktop data and retain old client access. It is not a home for new features or permanent desktop behavior. Remove it once support for these historical profiles and credentials ends.

## Ownership and entrypoints

- `migration.py`: `DesktopMigration.run` imports historical `config.json` servers, intersected grants, usage, activation, diagnostics and client setup. It preserves the original source, `config.before-python.json` backup and resumable `desktop-v2.json` migration journal, including deterministic import public paths. One runtime-owned instance retains its asynchronous lock so concurrent migration requests serialize safely.
- `tool_names.py`: `DesktopToolNames` repairs managed `desktop_<UUID>` and `import_<hash>` prefixes matching their generated public paths, and allocates readable collision-free prefixes during import. Explicit prefixes and failed repairs remain unchanged; rejected repairs retry on restart.
- `contracts.py`, `ports.py`: compatibility-only authorization/prefix-update commands and authorization-import/prefix-repair protocols. Orchestration depends on permanent desktop administration, naming, metadata and upstream preparation ports; it never imports backend adapters.
- `profile.py`: reads historical `config.json` agent hashes and gateway-port fallback. Permanent `endpoint.py` reads the current `python-endpoint.json`; `main.py` supplies the historical fallback only when needed.
- `authentication.py`: `LegacyAgentCredentials` matches retained SHA-256 agent hashes. Runtime injects this predicate into the permanent verifier; absent injection, only the current agent credential is accepted. Historical credentials never grant owner REST access.
- `adapters/legacy_host.py`: authenticates the old `runtime.json` management endpoint, verifies profile/PID identity and requests shutdown without signalling a PID from disk.
- `adapters/administration.py`: `BackendPrefixRepair` owns only historical prefix PATCH requests and error translation. Runtime supplies the permanent administration adapter’s HTTP client; that adapter retains ownership of closure.
- `adapters/oauth.py`: converts historical `upstream:oauth:*` Keychain records into current `python:oauth:*` authorization documents, preserving source records, expiry and refresh data without overwriting an existing target.

The initializers intentionally export nothing and import no backend code. Only the OAuth adapter imports the exact backend authorization document needed for conversion; the legacy-host adapter owns historical HTTP retirement and the prefix-repair adapter owns repair-only HTTP updates.

## Lifecycle

`main.py` retires the authenticated old host before binding the saved endpoint. `runtime.py` captures historical hashes only when not already persisted, then composes migration, naming repair and credential conversion. Startup enters REST, repairs names, enters MCP and restores upstreams in that order. Migration runs only through the authenticated `POST /desktop/migration` route, including native Swift callers. Shutdown ordering and permanent services are unchanged.

## Deletion checklist

- End support for historical config/runtime formats, generated tool prefixes, legacy OAuth Keychain records and migrated agent hashes; communicate endpoint and credential replacement requirements first.
- Remove legacy retirement and saved-port fallback imports/calls from `main.py`, retaining the current endpoint reader.
- Remove migration, repair, historical hash capture and credential-predicate injection from `runtime.py`, retaining current-token authentication and normal REST/MCP/upstream lifecycle.
- Remove `/desktop/migration` and its native Swift client/model call sites together; do not leave a broken native request.
- Remove this package and its dedicated tests, update architecture boundaries and README indexes, and retire persisted migration/hash metadata only with an explicit data-retention decision. Do not delete shared backend storage, source backups or Keychain credentials as incidental cleanup.
