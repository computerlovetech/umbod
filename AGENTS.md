# Umbod Instructions

Paths and commands below are relative to the repository root unless a working directory is specified.

## Agent Skills

Use Vercel's [skills.sh](https://skills.sh/) to install agent skills. Repository skill sources live in `skills/`; edit those, not installed copies in `.agents/skills/`.

## Releases

For Umbod release work, follow the manual [release-umbod skill](skills/development/release-umbod/SKILL.md).

## UI Components

Read the [component index](umbod/frontend/COMPONENT_INDEX.md) when working with UI Svelte components.

## Architecture decisions

Use the [ADR index](umbod/project/architecture-records/index.md) to find and read relevant accepted decisions before changing architecture. If in doubt, consult the ADRs.
Do not write an ADR unless the user asks for it.

## Source code index

Use the `write-module-readme` skill to maintain module `README.md` files and keep them up to date with module content.

- [Backend — API, MCP, and CLI](umbod/api/src/README.md)
- [Frontend — workspace UI](umbod/frontend/src/README.md)
- [SDK — connector development](packages/umbod-sdk/src/README.md)
- [Website — public site](website/src/README.md)

## Verification

Run the checks applicable to the changed area.

### API/MCP runtime

- For API or MCP application changes, run `bash umbod/tests/kind-runtime/run.sh` to verify running services in a disposable Kind cluster.
- If Kind service integration tests fail, inspect the runner's pod diagnostics, inspect the failing assertions resolve issues. The connector fixture and test-only values under `umbod/tests/kind-runtime/` must not enter the published chart or application images.

### Tests and static checks

- Python tests: `uv run umbod/scripts/run_tests.py <module>`. Modules: `all`, `cli`, `config`, `core`, `hosting`, `infrastructure`, `mcp`, `rest`, `messaging`, `deployment`. See `uv run umbod/scripts/run_tests.py --help` for defaults and pytest arguments.
- Analyse test timings: `uv run umbod/scripts/run_tests.py core --analyse`.
- Frontend: `cd umbod/frontend && bun run test && bun run check`
- Python lint: `cd umbod/api && uv run --locked ruff check .`

### Frontend UI

- From `umbod/`, run `docker compose build` and `docker compose up -d`, then verify UI changes with `agent_browser` at `http://localhost:3010` (not `file://`).
- After a rebuild, prefer separate `open`, `snapshot`, and `screenshot` calls over the `qa` preset.

### Helm chart

- For Helm chart changes, run both `umbod/deploy/helm/umbod/scripts/validate.sh` and `bash umbod/deploy/helm/umbod/scripts/kind-install-test.sh` before reporting the work as done.
- Run applicable negative schema checks when changing `values.yaml`, `values.schema.json`, or chart invariants.

### Semgrep

- Final check: `bash umbod/scripts/run_semgrep.sh`
- Quick check: `bash umbod/scripts/run_semgrep.sh <path> [more paths]`
- Run from the repo root. Add `--json` for JSON output. Fix reported errors and warnings.

## Review

After work is done, review the changes against the specification (if created) and relevant ADRs