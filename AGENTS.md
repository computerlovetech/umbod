# Umbod Instructions

Paths and commands below are relative to the repository root unless a working directory is specified.

## Agent Skills

Use Vercel's [skills.sh](https://skills.sh/) to install agent skills. Repository skill sources live in `skills/`; edit those, not installed copies in `.agents/skills/`.

## Architecture decisions

Architecture decision records live in [`umbod/project/architecture-records/`](umbod/project/architecture-records/). Read the applicable accepted ADRs before changing architecture; document intentional changes there rather than introducing a parallel pattern.

- [ADR-001: Backend-Neutral Persistence Module Boundaries](umbod/project/architecture-records/ADR-001-backend-neutral-persistence.md) — Read for database boundaries, migrations, or runtime lifetimes.
- [ADR-002: Client-Owned Credentials for Multi-Provider MCP Tool Authentication](umbod/project/architecture-records/ADR-002-client-side-credential-storage.md) (Proposed) — Read for MCP credential ownership and authentication.
- [ADR-003: Umbod-Specific Connector Development CLI](umbod/project/architecture-records/ADR-003-umbod-specific-connector-cli.md) — Read before adding SDK CLI commands.
- [ADR-004: One Backend API and a Thin Desktop Boundary](umbod/project/architecture-records/ADR-004-single-backend-api-and-desktop-boundary.md) — Read for backend APIs or Desktop integration.
- [ADR-005: One Workspace and Only Usable Controls](umbod/project/architecture-records/ADR-005-unified-workspace-and-usable-controls.md) — Read for navigation or control eligibility.
- [ADR-006: Filesystem Storage Infrastructure Boundary](umbod/project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Read for file storage, namespaces, or ownership persistence.
- [ADR-007: Actor-Specific Composition of Shared UI Components](umbod/project/architecture-records/ADR-007-actor-specific-ui-composition.md) — Read for shared components and actor-owned views.
- [ADR-008: Event-Synchronized In-Memory Tool Runtime](umbod/project/architecture-records/ADR-008-event-synchronized-tool-runtime.md) — Read before tool registration, discovery, routing, synchronization, or invocation changes.

## Where to start by task

Use the `write-module-readme` skill to maintain module `README.md` files and keep them up to date with module content.

- [Backend — API, MCP, and CLI](umbod/api/src/README.md)
- [Frontend — workspace UI](umbod/frontend/src/README.md)
- [SDK — connector development](packages/umbod-sdk/src/README.md)
- [Website — public site](website/src/README.md)

## Verification

Run the checks applicable to the changed area.

### API/MCP runtime

- For API or MCP application changes, run `bash umbod/tests/kind-runtime/run.sh` to verify running services in a disposable Kind cluster. Docker Compose is not a substitute.
- If Kind service integration tests fail, inspect the runner's pod diagnostics, report the failing assertions, and do not describe the integration suite as passing. The connector fixture and test-only values under `umbod/tests/kind-runtime/` must not enter the published chart or application images.

### Tests and static checks

- Backend suite: `cd umbod/api && uv run --locked pytest tests -q -n auto --maxprocesses=4 --dist=worksteal`. To select MCP tests, append `-k mcp`; for API tests, append `-k "not mcp"`.
- Serial execution/debugging: `cd umbod/api && uv run --locked pytest tests -q -n 0`. Use serial execution for small focused selections to avoid worker startup overhead. Parallel execution is explicit, not a global pytest default; keep Kind/live-runtime tests serial. Do not use uncapped `-n auto` or launch several full-suite runs concurrently.
- Python lint: `cd umbod/api && uv run ruff check .`
- Frontend tests, types, and Svelte checks: `cd umbod/frontend && bun run test && bun run check`

### Frontend UI

- From `umbod/`, run `docker compose build` and `docker compose up -d`, then verify UI changes with `agent_browser` at `http://localhost:3010` (not `file://`).
- After a rebuild, prefer separate `open`, `snapshot`, and `screenshot` calls over the `qa` preset.

### Helm chart

- For Helm chart changes, run both `umbod/deploy/helm/umbod/scripts/validate.sh` and `bash umbod/deploy/helm/umbod/scripts/kind-install-test.sh` before reporting the work as done.
- Run applicable negative schema checks when changing `values.yaml`, `values.schema.json`, or chart invariants.

### Semgrep

- Run the shared app Semgrep rules with `cd umbod && uv run semgrep scan --config ../.semgrep.yml .`.
- After each Semgrep run, resolve the reported issues, including pre-existing findings, and rerun the scan to verify the fixes.
- Do not add app-local Semgrep configs without an explicitly documented exception to the shared root `.semgrep.yml`.