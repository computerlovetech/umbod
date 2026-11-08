---
type: Software Module
title: Umbod Helm chart
description: Kubernetes workloads, private listeners, networking, storage, and chart verification.
---

# Umbod Helm chart

**Module responsibility:** Kubernetes deployment definition for the Umbod API, MCP server, frontend, networking, storage, and runtime configuration.

**Read when working with:** Kubernetes resources, chart values or schema, deployment security, ingress, persistence, or Helm validation.

## Submodules

### `templates/`

**Read when working with:** Rendered Kubernetes workloads, services, ingress, storage, service accounts, or chart tests.

### `ci/`

**Read when working with:** Values used to render and validate the chart in CI.

### `scripts/`

**Read when working with:** Automated chart validation or rendered-resource invariants.

- [Administrator MCP deployment](../../../docs/operations/admin-mcp.md) — Private separate hosting by default, shared opt-in, environment settings, and Compose configuration.
- [Administrator listener Service](templates/mcp-administrator.yaml) — Private ClusterIP networking enabled only for separate, enabled administrator hosting.
- [Administrator render validation](scripts/validate-mcp-administrator.py) — Hosting matrix, MCP ownership, ingress exclusion, and negative settings checks.
- [Collector resources](templates/telemetry.yaml) — Optional private OTLP Service targeting the API container's collector listener.
- [Collector render validation](scripts/validate-telemetry.py) — Enabled/default/custom-port topology and negative values checks.
- [Live OTLP verification](scripts/verify-otlp.py) — Public ingestion exclusion, private collector authentication and shared analytics assertions.

## Release policy

Canonical `umbod-v` tag pushes publish the SDK, then all three images, then this chart at one synchronized version. Stable three-component versions and `-beta.N` prereleases without leading zeros are accepted; the SDK uses PEP 440 beta spelling. The tag commit must be on `main` with successful exact-commit main-push CI. Chart version, appVersion, and core/frontend image tags are stamped together. Exact registry collisions stop publication; chart-only releases are not supported. Desktop releases remain independent.

## Deployment model

This chart deploys Umbod for development and evaluation. It runs API and MCP as two containers in a single, fixed one-replica `Recreate` Deployment. Both containers share SQLite storage at `/app/data`. The frontend runs in a separate Deployment.

## Storage limitation

The chart uses SQLite. SQLite, a shared ReadWriteOnce volume, and the fixed single-replica core are **development and evaluation only** and are not a production database architecture. Umbod provides no SQLite schema or persisted-data migrations; reset persistent storage before deploying an incompatible Umbod version. The chart does not install PostgreSQL or an authentication proxy.

## Install

Configure immutable image tags and any environment-specific origins in a values file, then install:

```sh
helm upgrade --install umbod ./deploy/helm/umbod -f values.local.yaml
```

The default repositories are configurable placeholders in `values.yaml`. Override `core.image` and `frontend.image` for published images used by your environment. The API and MCP containers use the same core image with different CLI commands.

## Connector plugins

The core image contains the connector SDK but no concrete connector plugins. By default, the chart starts Umbod without native plugins.

Set `plugins.image.repository`, `plugins.image.tag`, and `plugins.image.pullPolicy` to use an immutable plugin-bundle image. Set `plugins.availableConnectorIds` to the connector IDs from that bundle that the deployment may expose. The list defaults to empty and is authoritative: installing a plugin image alone does not make any connector available. Non-empty availability requires a complete plugin image configuration, and IDs must be non-blank and unique. The chart renders the existing `{"connectors":[{"id":"..."}]}` runtime contract into a ConfigMap, mounts the generated file read-only into API and MCP at `plugins.deploymentConfigurationPath`, and rolls out the core Pod when it changes. The chart first runs the plugin image as a materialization init container, mounting an ephemeral `/plugins` volume that the image populates. A second init container uses the configured core image to run `umbod connectors validate` against the mounted bundle. The API and MCP containers start only after validation succeeds, then mount the same volume read-only and discover its Python entry points through `PYTHONPATH`.

Validation checks declared SDK compatibility, entry-point loading, unique connector IDs, and SDK structural definitions. It does not inspect connector instance configuration, credentials, or external provider availability.

The plugin image must implement the plugin-bundle materialization contract: it must populate its `/plugins` mount and exit successfully. It must include plugin distribution metadata but not its own copy of the connector SDK, so validation and runtime use the SDK from the core image. A configured repository requires a non-empty tag. Use the same release compatibility constraints for Python version, operating system, and CPU architecture.

Sensitive configuration is never rendered by this chart. Create a Secret separately and set `existingSecret`; only API and MCP consume it with `envFrom`. The static frontend never receives this Secret. The existing Secret must contain `UMBOD_ROOT_SECRET` and `UMBOD_OIDC_CLIENT_SECRET`. Backend purpose-specific secrets are derived from `UMBOD_ROOT_SECRET`.

Set non-secret runtime configuration through the typed `config` values. Set `config.features.mcp.administratorEnabled` to `false` to prevent the privileged MCP administrator tools from being registered while leaving ordinary MCP tools available. `core.api.env` and `core.mcp.env` are final backend overrides. Always use immutable image tags; do not use floating tags.

The frontend is static output served by non-root nginx on port 3000; Bun is used only to build the image. At startup, jq generates `/app-config.json` containing only `apiBaseUrl` and `mcpBaseUrl`, from `PUBLIC_API_BASE_URL` and `PUBLIC_MCP_BASE_URL`. `frontend.apiBaseUrl` defaults to same-origin `/api`; `config.publicOrigins.mcp` supplies the browser MCP URL. The browser API base must be publicly reachable, never an internal Service hostname. `config.publicOrigins.site`, `.api`, and `.mcp` remain backend public-origin settings. The frontend health endpoint is static and does not contact Python. Deep links use `200.html`; missing `/_app/` assets return 404, immutable assets use long-lived caching, and shell/config responses use no-store. See [static runtime](../../../frontend/deployment/README.md).

Migration: remove `frontend.bodySizeLimit`, `frontend.privateAuthTokenHeader`, and `frontend.env` from existing values files; schema validation now rejects them. Node `PORT`, `ORIGIN`, private API/auth headers, and body-size-limit variables no longer apply. The frontend container port is fixed at 3000; its Service port remains configurable. API request limits and authentication belong to Python and the external gateway.

The default standalone configuration uses an ephemeral `emptyDir` volume for SQLite, so data is lost when the core Pod is replaced. Set `persistence.enabled=true` to create a 1 Gi ReadWriteOnce claim. Configure `persistence.size`, `persistence.storageClass`, and `persistence.accessModes` as needed, or select an existing ReadWriteOnce claim with `persistence.existingClaim`.

Configure analytics through `config.telemetryAnalytics.enabled` (default `false`) and `config.telemetryAnalytics.sqlitePath` (default `/app/data/analytics.sqlite3`). Only the API container receives these settings. Analytics uses its own SQLite file, schema and lifecycle, never application persistence or its migrations. The files share the mounted data volume, so analytics is ephemeral unless persistence is enabled; no separate analytics PVC is created. The schema requires a canonical file beneath `/app/data` and rejects the default application database and its sidecars. Final `core.api.env` overrides remain supported without duplicate analytics environment entries. Enabling analytics does not enable the OTLP receiver or supply credentials. See [analytics backend configuration](../../../docs/operations/configuration.md#analytics-backend) for collection prerequisites and storage boundaries.

## Networking

ClusterIP Services expose API, public MCP, administrator MCP, and frontend internally by default. Administrator MCP is private and can be disabled or moved to shared hosting. With the `umbod` release name, they are `umbod-api`, `umbod-mcp`, `umbod-mcp-administrator`, and `umbod-frontend`. Other release names prefix the chart name unless they already contain it; `fullnameOverride` replaces that prefix. Workload Pods disable Kubernetes service-link environment variables to prevent Service names such as `umbod-mcp` from colliding with application port settings. The optional `networking.k8s.io/v1` Ingress is disabled by default. Set `ingress.enabled`, `ingress.className`, `ingress.host`, path values, annotations, and TLS entries for the target cluster. The Ingress routes RFC 9728 protected-resource discovery and the MCP OAuth authorization endpoints directly to the MCP Service. The `/api` path is fixed and routes directly to Python's authenticated browser aliases without stripping the prefix, never to the SPA fallback. Do not add rewrite/strip-prefix annotations. The chart does not install an authentication proxy: configure an external gateway with route-specific website session authentication and nonredirecting API 401 responses. Do not blanket-apply website authentication or rewrites to MCP OAuth/discovery using the shared ingress annotations. Backend issuer/audience validation must remain enabled for direct bearer clients at the exposed public API origin. Set `config.authentication.oidc.issuerUrl` when the issuer cannot be derived from an Auth0 domain; production Entra and Google configurations require this explicit issuer. Set `config.authentication.oidc.audience` to the intended API audience. Align website OIDC configuration with backend token expectations; oauth2-proxy `--set-authorization-header` forwards ID tokens. Gateways forwarding JWT access tokens should select their verified token header through `config.authorization.adminJwtHeader`; cookie-free native clients can still use `Authorization` when that configured header is absent. The frontend's nginx API proxy also supports local Service port-forwards and resolves the backend Service under the standard `cluster.local` DNS domain.

Public REST excludes `/v1/*` ingestion routes, and Ingress never routes `/v1` to a receiver. Collection is disabled by default.

Set `telemetry.enabled=true` to add the private collector listener to the existing API container and expose it through a ClusterIP Service targeting the core Pod. `telemetry.port` and `telemetry.servicePort` default to 4318 and independently select the listener and Service ports. `telemetry.bearerTokenSecret.name` is required and references a separately managed Secret; `.key` defaults to `UMBOD_OTLP_BEARER_TOKEN`. Only API receives this dedicated key, not MCP. The chart manages receiver enablement, host, port and token; do not override these through container environment values.

`umbod api serve` serves public REST and private collection in one process and event loop. Both enabled primary listeners must start for readiness; failure stops siblings. Collector writes and administrator reads share the host-owned analytics runtime configured through `config.telemetryAnalytics`. Core `persistence` controls durability of its separate SQLite file on `/app/data`. There is no standalone collector Deployment, image, resource allocation or PVC. The retired `telemetry.image`, `telemetry.analytics`, and `telemetry.persistence` settings are unsupported. Independently deployed `umbod telemetry serve` remains available outside this chart, but its analytics history is not automatically dashboard-visible. See [telemetry ingestion](../../../docs/reference/telemetry-ingestion.md) for all three signal endpoints, gzip, limits, and sensitive payload handling.

## Security and operations

Pods disable service-account token mounting, use the RuntimeDefault seccomp profile, prevent privilege escalation, and drop Linux capabilities. The frontend runs as nginx UID/GID 101 with non-root enforcement and writable temporary paths. Backend images do not yet force a numeric user; read-only root filesystems are not enabled. Resource requests, limits, HTTP readiness probes, and HTTP liveness probes are enabled by default.

Run the chart tests after installation:

```sh
helm test umbod
```

The tests verify API, MCP, and independent frontend health through their ClusterIP Services, runtime public configuration caching, deep-link SPA routing, and missing asset/API 404 behavior. They also verify RFC 9728 protected-resource metadata, OAuth authorization-server metadata, and the MCP `WWW-Authenticate` discovery challenge. When plugins are configured, an additional test checks that the running API loaded only the selected plugins.

Run the same Docker-based Kind installation used by CI from `umbod/`:

```sh
deploy/helm/umbod/scripts/kind-install-test.sh
```

The script builds the core and frontend images, creates a Kubernetes 1.32 Kind cluster, loads the images, installs the chart without connector plugins using `ci/kind-values.yaml`, verifies analytics environment configuration and separate initialized SQLite schemas in the running API, and runs the Helm tests. It then verifies public ingestion is absent, enables the co-hosted private collector with custom container/Service ports and a generated token Secret, checks authentication and shared analytics through the API, verifies MCP lacks the dedicated token, and checks core persistent storage across Pod replacement. Archive mode requires both `--core-image-archive` and `--frontend-image-archive`. It deletes the cluster afterward. Set `UMBOD_KIND_KEEP_CLUSTER=true` to retain the cluster for investigation.

## Validation

Run the validation script from any directory:

```sh
umbod/deploy/helm/umbod/scripts/validate.sh
```

The script runs strict Helm linting, renders the chart with the CI values, validates the Kubernetes resources with kubeconform and the chart-specific validators, checks analytics defaults, enablement, path overrides and negative schema cases, validates default and custom-port co-hosted collector rendering, API-only token injection, public ingress exclusion and invalid collector settings, and verifies that the chart can be packaged. Temporary rendered and packaged artifacts are removed automatically.

CI runs three independent Helm jobs. Chart validation lints, renders, checks architecture, and packages the chart. Schema validation runs kubeconform against Kubernetes 1.25, the chart's minimum supported version, and Kubernetes 1.32, 1.33, and 1.34. Installation validation invokes `scripts/kind-install-test.sh`, which builds core and frontend images in the Kind job without uploading artifacts. The same script performs local and CI cluster creation, image loading, chart installation, workload waiting, Helm tests, diagnostics, and cleanup.
