# Umbod Desktop

Native SwiftUI (Apple Silicon, macOS 14+) and WPF (Windows 10/11 x64) interfaces share a Rust MCP gateway. Desktop is a single-user, local-first application with tool permissions shared across connected agent clients. It is independent of the Kubernetes services in `umbod/` and does not require their deployment.

No public desktop release is advertised yet. The website deliberately offers self-hosting until a verified desktop release manifest is reviewed and applied. Local builds and the manual release workflow currently support **unsigned prereleases only**: macOS is ad-hoc signed and not notarized; Windows is unsigned. Do not disable OS security protections to run a build.

## Build and test

Run from the monorepo root unless a command explicitly changes directory. Prerequisites: stable Rust (including rustfmt and Clippy), Python 3, Swift 6 and Apple developer tools on macOS; .NET 8 SDK and PowerShell 7 on Windows. No command below installs or launches the production app.

```sh
cd desktop
export PATH="$HOME/.cargo/bin:$PATH"
cargo test --locked
cargo fmt --check
cargo clippy --locked --all-targets -- -D warnings
swift build --package-path native
swift run --package-path native UmbodTests
bash scripts/build.sh           # dist/Umbod Dev.app, ad-hoc signed
bash scripts/package.sh         # dist/Umbod-<VERSION>-arm64.dmg
```

The Swift tests are an executable assertion harness, not `swift test`. Tests use temporary directories and randomly named fixture credentials in the OS vault, and require local socket and vault access. Do not run them against installed app data. `scripts/verify.sh` runs the Mac checks. Optional `scripts/native-smoke.py` requires a built app and launches only that app with temporary data; it never launches `/Applications/Umbod.app`.

Windows (from `desktop/` in PowerShell):

```powershell
$env:DOTNET_GENERATE_ASPNET_CERTIFICATE = 'false'
$env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = '1'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
cargo test --locked
dotnet run --project windows/Umbod.Core.Tests -c Release -- --gateway "$PWD/target/debug/umbod-gateway.exe"
python scripts/test_windows_package.py
./scripts/package-windows.ps1 -Channel release
```

The ZIP is self-contained; extract the entire archive before running `Umbod.Windows.exe`. Its `--smoke-test` mode constructs the WPF window without starting a gateway or accessing application data. Cross-publishing WPF on macOS proves compilation only; native Windows CI builds the Windows Rust gateway, runs Core integration and the packaged WPF smoke test. Local stdio connectors on Windows must use an executable such as `node.exe`, with explicit arguments; `.cmd`/`.bat` wrappers are not supported.

Repository policy and website checks:

```sh
python3 -m unittest discover -s desktop/tests -v
node --test website/tests/*.test.mjs
cd website && bun run build
```

## Use and lifecycle

Add local executable or remote Streamable HTTP connectors, rediscover their tools, then explicitly enable tools. New tools start disabled. Permission changes apply to subsequent calls from every connected client. Settings → MCP provides bridge configuration. Credentials remain in macOS Keychain or Windows Credential Manager; there is no plaintext fallback.

Closing the UI leaves the background gateway running. Settings can stop or restart it. Development and release profiles have separate data and vault namespaces (`app.umbod.desktop.dev` and `app.umbod.desktop`). Builds do not migrate, reset, or install app data. There is no automatic update or login supervisor.

OAuth supports native public clients with loopback callbacks, discovery, PKCE and refresh. Real OAuth providers are not certified. Legacy standalone SSE upstreams, resources, prompts, sampling, and tool argument-level policies are unsupported. Desktop does not claim the Kubernetes edition's organization identity or group administration capabilities.

## Code and release index

- `backend/src/`: Rust gateway, profiles, platform adapters, client setup and OAuth; `backend/tests/`: integration tests.
- `native/`: SwiftUI app and Swift contract/lifecycle tests.
- `windows/`: shared .NET Core contracts, Core tests, and WPF app.
- `scripts/`: local builds, packaging, isolated fixtures, and release policy/metadata.
- `VERSION`: independent desktop version; keep Cargo.toml and the gateway entry in Cargo.lock synchronized. Bundle, package and .NET versions derive from it.
- [Release procedure](docs/RELEASING.md), [manifest application](docs/APPLY-MANIFEST.md), and [import provenance and audit](docs/PROVENANCE.md).

The [upstream Windows run](https://github.com/kasperjunge/umbod-desktop/actions/runs/37907078176) is historical source evidence supplied for this import. It is **not** a CI result for this target repository or these integration changes.
