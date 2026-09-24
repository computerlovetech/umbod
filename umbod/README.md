# Umbod

The product vision and strategy live in `docs/VISION.md` and `docs/STRATEGY.md`.

Starter app with the same high-level layout as `apps/computerlove-tech`:

- `api/` — Python package with FastAPI, FastMCP, and Typer CLI entrypoints.
- `frontend/` — SvelteKit app served with adapter-node.
- `docker-compose.yml` — API, MCP, and frontend services.

## Feature roadmap

**Legend:** ✅ Complete · 🚧 In progress · ⬜ Planned · 🟢 Stable · 🟡 Evolving · ⚪ Not assessed

| Feature | Delivery | Stability | Scope |
| --- | :---: | :---: | --- |
| Connector administration | ✅ Complete | 🟡 Evolving | Configure, publish, and unpublish registered connectors from the admin UI. |
| Dynamic MCP tool publication | ✅ Complete | 🟡 Evolving | Reconcile connector tools into the running MCP server without restarting it. |
| OpenAPI connectors | ✅ Complete | 🟡 Evolving | Create connectors from OpenAPI documents and configure their authentication. |
| Downstream MCP connectors | ✅ Complete | 🟡 Evolving | Register downstream MCP servers and expose their tools through Umbod. |
| Group permissions | ✅ Complete | 🟡 Evolving | Manage group-level access to MCP tools from the admin UI. |
| Authentication and deployment profiles | ✅ Complete | 🟡 Evolving | Support local development authentication and production OIDC-based deployments. |
| Helm chart for Kubernetes | ⬜ Planned | ⚪ Not assessed | Install and configure Umbod on Kubernetes using Helm. |
| Tool description overrides | ⬜ Planned | ⚪ Not assessed | Override published tool descriptions from the `/admin` interface. |
| Configurable `toolPolicy` | ⬜ Planned | ⚪ Not assessed | Configure tool access policies as `allow`, `ask`, or `blocked`, controlling whether tools run directly, require approval, or cannot be used. |
| Agent observability tools | ⬜ Planned | ⚪ Not assessed | Provide built-in tools such as `give_feedback` and `self_diagnose` for agent feedback and diagnostics. |
| Per-connector runtime logging configuration | ⬜ Planned | ⚪ Not assessed | Configure logging levels independently for each connector at runtime. |

## Development setup

Clone the full monorepo rather than this directory alone. The API and container builds depend on packages elsewhere in the repository.

### Prerequisites

Everyday development uses:

- Git.
- Docker Engine with Docker Compose v2.
- Python 3.14 or newer. The repository pins Python 3.14 in the root `.python-version`.
- [uv](https://docs.astral.sh/uv/) for Python environments, dependencies, commands, tests, linting, and documentation.
- [Bun](https://bun.sh/) for frontend dependencies, scripts, tests, and checks. Do not use npm, pnpm, or Yarn in `frontend/`.
- curl for command-line health checks.

Kubernetes and Helm chart development additionally requires:

- Helm 3.
- kubeconform.
- Kind.
- kubectl.

The chart supports Kubernetes 1.25 or newer. CI currently uses Helm 3.17.3, kubeconform 0.6.7, Kind 0.27.0, and a Kubernetes 1.32 Kind node.

### Run the complete local stack

From `apps/umbod`:

```bash
docker compose build
docker compose up -d
docker compose ps
curl --fail http://localhost:18010/system/health
```

No `.env` file is required for the default local development profile. The stack uses SQLite in the `umbod-data` Docker volume and simulated development authentication.

- Admin UI: `http://localhost:3010`
- API health: `http://localhost:18010/system/health`
- MCP server: `http://localhost:8011`

Stop the stack with `docker compose down`. Use `docker compose down --volumes` when the local SQLite data and plugin volumes should also be removed.

Production authentication can be exercised with `docker compose --profile auth up -d` after configuring the Auth0 values from `.env.example`.

### Run services from source

Install API dependencies from `apps/umbod/api`:

```bash
uv sync
```

Run the API and MCP server in separate terminals:

```bash
uv run umbod api serve --reload
uv run umbod mcp serve --reload
```

Install and run the frontend from `apps/umbod/frontend`:

```bash
bun install --frozen-lockfile
bun run dev
```

### Checks

Run the checks for the area being changed:

```bash
cd api
uv run pytest tests -k mcp
uv run pytest tests -k "not mcp"
uv run ruff check .

cd ../frontend
bun run test
bun run check
```

Run the shared Semgrep rules from `apps/umbod`:

```bash
uv sync --group dev
uv run semgrep scan --config ../.semgrep.yml .
```

### Documentation

The static solution documentation is maintained in `docs/` and built with MkDocs Material. From `apps/umbod`:

```bash
uv sync --group dev
uv run mkdocs serve
uv run mkdocs build --strict
```

The authoring server is available at `http://127.0.0.1:8000`.

### Helm chart validation

Run static chart validation from `apps/umbod`:

```bash
deploy/helm/umbod/scripts/validate.sh
```

This requires Helm, kubeconform, and Python 3. Run the Docker-backed installation test with:

```bash
deploy/helm/umbod/scripts/kind-install-test.sh
```

The installation test requires Docker, Helm, Kind, and kubectl. It creates and removes a Kind cluster. Set `UMBOD_KIND_KEEP_CLUSTER=true` to retain a failed test cluster for investigation.

## Configuration

Configuration is driven by a small set of intent-based environment variables. The pydantic
`OperatorSettings` model is the only user-facing surface; it is mapped into an internal
`AppConfig` domain model that the API and MCP server consume.

- `UMBOD_PROFILE`: `local` (default) or `production`.
- `UMBOD_AUTH`: `dev` (default when local), `auth0`, `entra`, or `google`.
- Topology origins (`UMBOD_PUBLIC_SITE_ORIGIN`, `UMBOD_PUBLIC_API_ORIGIN`,
  `UMBOD_PUBLIC_MCP_ORIGIN`, `UMBOD_INTERNAL_API_ORIGIN`) drive the derived
  API/MCP URLs, CORS origins, OIDC discovery/JWKS URLs, and the oauth2-proxy redirect.

Local runs need no `.env`: `docker compose up` starts the `local`/`dev` profile with a
SQLite store and a simulated admin. `.env.example` is the production checklist.

Inspect the resolved configuration (secrets redacted):

```bash
uv run umbod config validate
uv run umbod config show            # summary
uv run umbod config show --advanced # full resolved config
```

## Endpoints

- Health: `GET /system/health`
- MCP card: `GET /.well-known/mcp/server-card.json` on `UMBOD_PUBLIC_MCP_ORIGIN`
