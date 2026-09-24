# Umbod Instructions

## Where to start by task

Start at the boundary exposing the behavior, use that module's `README.md` as its local index, follow calls into `api/src/umbod/core/`, and inspect `infrastructure/` or other adapters only for external I/O. Update affected module `README.md` indexes when responsibilities, entrypoints, or submodule structures change.

- REST/API behavior → `api/src/umbod/rest/`; MCP behavior → `api/src/umbod/mcp/`; CLI behavior → `api/src/umbod/cli/`.
- Connector authoring API → `api/src/connectors/` is the public API for users building connectors to deploy in Umbod; read `api/src/connectors/README.md` and `../packages/umbod-sdk/src/umbod_sdk/skills/draft-agent-connector/SKILL.md` before changing it or creating a connector.
- Messaging/events → `api/src/messaging/`.
- Pages/navigation → `frontend/src/routes/`; reusable UI → `frontend/src/lib/components/`; frontend administration APIs and state → `frontend/src/lib/admin/`.
- Configuration → `api/src/umbod/config/`, then `docker-compose.yml` or Helm when deployment wiring is involved.
- Local service wiring → `docker-compose.yml`; Kubernetes deployment → `deploy/helm/umbod/`.
- Defects → begin at the failing public behavior or test, find its nearest boundary, then trace inward; do not choose files by name alone.

## Runtime verification

- When changing application code, run `docker compose build` and `docker compose up -d` from `apps/umbod` before reporting the work as done.
- For service-specific fixes, inspect the relevant container logs with `docker compose logs <service>` and verify the changed service starts successfully.

## Tests and static checks

Run the checks applicable to the changed area:

- MCP: `cd api && uv run pytest tests -k mcp`
- API: `cd api && uv run pytest tests -k "not mcp"`
- Python lint: `cd api && uv run ruff check .`
- Frontend tests: `cd frontend && bun run test`
- Frontend type and Svelte checks: `cd frontend && bun run check`
- Running-service integration tests, after starting Docker Compose: `cd api && uv run pytest live_runtime_tests`

## UI inspection

- From `apps/umbod`, run `docker compose build` and `docker compose up -d`, then verify UI changes with `agent_browser` at `http://localhost:3010` (not `file://`).
- After a rebuild, prefer separate `open`, `snapshot`, and `screenshot` calls over the `qa` preset.

## Helm chart verification

- Whenever changing the Helm chart, run `deploy/helm/umbod/scripts/validate.sh` before reporting the work as done.
- Whenever changing the Helm chart, run `deploy/helm/umbod/scripts/kind-install-test.sh` from `apps/umbod`. This is the same Docker-based Kind installation and Helm test entrypoint used by CI.
- Run applicable negative schema checks when changing `values.yaml`, `values.schema.json`, or chart invariants.

## Semgrep

- Run the shared app Semgrep rules from this directory with `uv run semgrep scan --config ../.semgrep.yml .`.
- The shared Semgrep config lives at `apps/.semgrep.yml`; do not add app-local `.semgrep.yml` files unless the app needs an explicitly documented exception.
