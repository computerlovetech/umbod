# Umbod Desktop

The macOS-only native SwiftUI app (Apple Silicon, macOS 14+) uses the shared Python REST/MCP backend through a desktop host in `python/`. Desktop is a single-user, local-first application with tool permissions shared across connected agent clients. macOS bundles its Python interpreter and dependencies; running the app requires neither Docker nor a separately installed Python. It does not require a Kubernetes deployment.

Verified desktop releases are available from https://umbod.ai/download/. Local builds and the manual release workflow currently support **unsigned prereleases only**: macOS is ad-hoc signed and not notarized. Do not disable OS security protections to run a build.

## Build and test

Run from the monorepo root unless a command explicitly changes directory. Build prerequisites: uv, Python 3.11+, and full Xcode with Swift 6 or newer on Apple Silicon macOS; Command Line Tools alone are insufficient. Install Xcode and open it to finish first-launch setup and accept its license. Select the installation with `DEVELOPER_DIR` or `sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer`. Run `bash desktop/scripts/check-macos-toolchain.sh` to verify the selection and SwiftUI macros before building. On Apple Silicon macOS, `nix develop .#desktop` supplies the normal repository tools and pinned Python/uv environment and checks the external Apple compiler and SDK; it does not install Swift, Xcode, or an SDK. The general `nix develop` shell has no Xcode requirement. Packaging downloads a pinned CPython 3.14.3 runtime and verifies its SHA-256. No command below installs or launches the production app.

```sh
cd desktop
bash scripts/verify.sh          # Python tests, dev bundle, Swift contracts
bash scripts/build.sh           # dist/Umbod Dev.app, ad-hoc signed
bash scripts/package.sh         # dist/Umbod-<VERSION>-arm64.dmg
```

The Swift tests are an executable assertion harness, not `swift test`. Tests use temporary directories and an explicitly selected fixture credential store, and require local socket access. Routine Mac tests never access the user’s Keychain. Real app profiles continue to require Keychain, with no plaintext fallback. Do not run them against installed app data. `scripts/verify.sh` runs the Mac checks.

Repository policy and website checks:

```sh
python3 -m unittest discover -s desktop/tests -v
node --test website/tests/*.test.mjs
cd website && bun run build
```

## Install the current code locally

Run `python3 desktop/scripts/install-local.py` from the repository root to build and install the release app into `/Applications/Umbod.app`, then reopen it. Use `--dry-run` to preview the steps without changing anything. This is an explicit production install; it does not install or stop Umbod Dev.

The script verifies the staged bundle before quitting the installed UI and stopping its authenticated gateway. Active production tool calls are interrupted during replacement. It retains the previous app under `/Applications/.umbod-local-backups/<timestamp>/Umbod.app` and restores it if the bundle replacement fails. A startup failure leaves the new app installed for inspection and reports the retained backup; it does not roll back application data. Backups are retained until you remove them.

Connections and permissions remain in `~/Library/Application Support/Umbod`; secrets remain in Keychain. New code uses that real production profile, so this is not an isolated test and does not snapshot database migrations. Run as your normal user with write access to the installation location, never with `sudo`. Local builds remain ad-hoc signed and unnotarized; the script does not bypass macOS security checks.

The local installer writes a short-lived quit request in the private profile directory, bound to the running UI's PID and bundle path. The native app receives it in modal run-loop modes, dismisses its SwiftUI presentations, and quits normally. Older builds fall back to the standard macOS quit request; a blocked quit leaves the installed bundle untouched and explains how to retry.

## Use and lifecycle

Add local executable or remote Streamable HTTP connectors. Saving an HTTP connector presents sign-in options when the server requests authentication; successful sign-in automatically discovers tools. The setup sheet then leads to tool selection. Browser attempts can be cancelled independently, and their links can be reopened or copied to another browser profile. Connection settings distinguish provider permissions from enabled tools and expose safe setup diagnostics. Enable individual tools, select multiple or filtered tools, or review the connector-wide Enable all / Disable all action. Confirmations list the exact affected tools. Provider-supplied read-only annotations are review hints, not security guarantees. New tools start disabled. Saved tool choices survive failed discovery and authorization reconnection; reconnecting restores those choices for tools still present. Tool toggles update immediately while an ordered background queue saves permission changes; the fixed-space saving indicator does not shift the controls. Failed saves show an error and reconcile with the backend without dropping later edits. Permission changes apply to subsequent calls from every connected client once saved. Settings → MCP provides bridge configuration and a copyable setup prompt pointing to the shared `umbod://setup/agent-instructions` MCP resource. The agent applies that guidance to its user-scoped instruction file across projects; Umbod does not edit the file. Credentials remain in macOS Keychain; there is no plaintext fallback.

On macOS, first launch imports existing `config.json` with a resumable journal and preserves the source and a `config.before-python.json` backup. Existing Keychain entries are retained. Import failures remain visible and retry on reopening/restarting; restore missing credentials or executables first. The saved MCP port and existing agent token hashes remain valid. Shared-backend tool names can differ, so clients should refresh their tool catalogs. The old `umbod-gateway` command remains a Python launcher for existing bridge configurations.

Public tools use a readable connector prefix derived by Python, for example `Dinero_get_invoice`. On backend startup, existing generated `desktop_<UUID>` and `import_<hash>` prefixes are repaired without reconnecting or recreating the connector. Custom prefixes remain unchanged. Refresh connected agents' tool catalogs after upgrading; old generated tool names are not retained as aliases. Duplicate names encountered during import or repair receive numeric suffixes. New connections use the shared backend's publication collision checks; give separate accounts descriptive names such as `Dinero Work` and `Dinero Personal` when their tool names overlap.

Settings → Advanced reads the running exposure mode and administrator MCP feature state from the authenticated backend. Choose `gateway` (default/recommended: `search_tools` + `execute_tool`), `flat` (individual enabled tools), or `codemode` (`search_tools` + `execute_code`). Uploaded-file tools currently require `flat`, which can increase startup/context size. Administrator MCP is off by default; enabling requires confirmation because every agent using the Desktop token can read and change connector configuration, activation, policy and grants. **Save and restart connection** durably saves both values in the profile's backend-owned `desktop-v2.json`, stops the backend, starts it and verifies health and effective settings. Pending values are not reported as active before verification. Connected MCP clients may need a new session or tool-catalog refresh. A failed restart retains saved settings and profile data: retry the action, or use Start in General settings after resolving the reported problem. Never delete the profile/database or credentials as a restart workaround.

Exposure selection does not add connector installation or native setup screens: the desktop editor still manages downstream MCP connections only, and built-in catalog connectors remain unavailable. OpenAPI connectors provisioned through the shared administration API require `codemode` for MCP discovery and execution; they do not appear in the native connector inventory. Administrator MCP does not install catalog connectors.

When the connection is stopped in General settings, start it there before saving Advanced changes. Advanced restart recovery is available offline only for an already-saved draft after an unverified restart.

Closing the UI leaves the background gateway running. Settings can stop or restart it. Development and release profiles have separate data and vault namespaces (`app.umbod.desktop.dev` and `app.umbod.desktop`). Builds do not migrate, reset, or install app data. Release apps check the published desktop manifest on launch and at most once daily while open. Settings provides a manual update check, an automatic-check preference, release notes, and a guided installer download/quit flow. Users can defer or skip a version; manual checks show skipped versions again. Development builds default to manual checks, and test-credential app sessions never check online. Updates are not installed automatically, and there is no login supervisor.

OAuth supports native public clients with loopback callbacks, discovery, PKCE and refresh. Real OAuth providers are not certified. Legacy standalone SSE upstreams, upstream resources and prompts, sampling, and tool argument-level policies are unsupported. Desktop does not claim the Kubernetes edition's organization identity or group administration capabilities.

Older installed versions that require a Windows asset in update metadata cannot read new macOS-only manifests. Download the first macOS-only release manually from the website; its updater accepts both historical and macOS-only manifests. Existing published releases are not changed.

## Shared composition

The Python host uses the backend-owned [`umbod.hosting`](../umbod/api/src/umbod/hosting/README.md) API also used by the separate Kubernetes REST/MCP services. Native lifecycle and credential ownership remain desktop-specific. Desktop migration and tool-name repair live exclusively in the removable [`backward_compatibility`](python/umbod_desktop/backward_compatibility/README.md) package, alongside old-host retirement, historical profile fallback, OAuth conversion and migrated token matching. Compatibility orchestration and permanent usage recording depend on desktop-owned typed ports; concrete shared HTTP, hosting, transport and OAuth adapters live in `python/umbod_desktop/backend_integration/`. The Python index documents the exact remaining naming, configuration and OAuth persistence coupling; the compatibility index owns historical formats, lifecycle entrypoints and concrete removal steps.

## Code and release index

- [`python/`](python/README.md): macOS host, transport adapters, Keychain, migration and tests; reuses `umbod/api` and `packages/umbod-sdk`.
- `native/`: SwiftUI app and Swift contract/lifecycle tests; `UmbodCore/AdvancedSettings.swift` owns backend-reported pending/effective settings, confirmation and verified restart/recovery, while `Umbod/AdvancedSettingsView.swift` presents Settings → Advanced; Settings provides compact update controls and generic stdio/HTTP connection details, with the bearer token masked and available only through an explicit copy action. Connector authentication stays optional and credentials remain in Keychain; `UmbodCore/ConnectorEditor.swift` owns the actual editor submission and retry state; `UmbodCore/ToolPermissionQueue.swift` owns optimistic permission edits, ordered save state, and stale-refresh protection; `UmbodCore/DesktopUpdate.swift` validates update metadata and `Umbod/UpdatesView.swift` owns update preferences and the install guidance.
- `scripts/`: local builds, packaging, isolated fixtures, and release policy/metadata; `check-macos-toolchain.sh` owns the shared full-Xcode, Swift 6, SDK and SwiftUI macro preflight used by builds, verification, acceptance preparation and the desktop Nix shell.
- `VERSION`: independent desktop version; the single source for bundle and package versions.
- [Release procedure](docs/RELEASING.md), [manifest application](docs/APPLY-MANIFEST.md), and [import provenance and audit](docs/PROVENANCE.md).
- [0.2.4 release candidate](docs/releases/0.2.4.md): announcement draft and release-owner acceptance checklist; not a publication record.

Release packaging collects dependency inventories and notices through `scripts/dependency-notices.py`; pinned supplemental sources are documented in `licenses/README.md`. `scripts/verify-python-bundle.py` rejects editable installs and imports outside the bundled interpreter before signing and again after installation. `scripts/audit-macos-bundle.py` verifies ARM64 slices, the macOS 14 deployment floor, required resources, executable permissions, internal symlinks and relocatable native dependencies. `Resources/build-metadata.json` records source and toolchain inputs. `scripts/prepare-macos-acceptance.sh` packages a precompiled test harness and fixtures; the separate `macos-acceptance` job runs `scripts/accept-macos-artifact.sh` on current macOS ARM64 with no checkout, using the DMG’s interpreter for backend and bundle checks. This required job also runs in the manual release workflow before publication. `scripts/install-smoke.py` installs the Mac DMG into disposable storage and verifies the packaged connector/agent flow, persistence, and signature integrity before and after execution. It never uses the login Keychain.

Automated click-through and window-lifecycle UI tests are currently removed. The remaining checks do not launch or interact with the SwiftUI app. `scripts/verify-macos-bundle.sh` validates bundle executables, Python isolation, and metadata during builds. Verify connector creation/editing, tool enablement, and browser sign-in manually until focused UI tests are reintroduced.
