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

Sensitive configuration is never rendered by this chart. Create a Secret separately and set `existingSecret`; all application containers consume it with `envFrom`. The existing Secret must contain `UMBOD_ROOT_SECRET` and `UMBOD_OIDC_CLIENT_SECRET`. Backend purpose-specific secrets are derived from `UMBOD_ROOT_SECRET`.

Set non-secret runtime configuration through the typed `config` values. Set `config.features.mcp.administratorEnabled` to `false` to prevent the privileged MCP administrator tools from being registered while leaving ordinary MCP tools available. `core.api.env`, `core.mcp.env`, and `frontend.env` are final per-component overrides. Always use immutable image tags; do not use floating tags.

The frontend reads `PUBLIC_MCP_BASE_URL` when the container starts, and adapter-node reads the public site origin from `ORIGIN`. Browser API requests use same-origin frontend routes, while server API requests use `PRIVATE_API_BASE_URL`. The chart derives all of these from `config`, so one immutable frontend image can be used across installations.

The default standalone configuration uses an ephemeral `emptyDir` volume for SQLite, so data is lost when the core Pod is replaced. Set `persistence.enabled=true` to create a 1 Gi ReadWriteOnce claim. Configure `persistence.size`, `persistence.storageClass`, and `persistence.accessModes` as needed, or select an existing ReadWriteOnce claim with `persistence.existingClaim`.

## Networking

Three ClusterIP Services expose API, MCP, and frontend internally. The optional `networking.k8s.io/v1` Ingress is disabled by default. Set `ingress.enabled`, `ingress.className`, `ingress.host`, path values, annotations, and TLS entries for the target cluster. The Ingress routes RFC 9728 protected-resource discovery and the MCP OAuth authorization endpoints directly to the MCP Service. Path handling depends on the selected ingress controller and application configuration.

## Security and operations

Pods disable service-account token mounting, use the RuntimeDefault seccomp profile, prevent privilege escalation, and drop Linux capabilities. The chart does not force a numeric user or read-only root filesystem because compatibility with the current images is not established. Resource requests, limits, HTTP readiness probes, and HTTP liveness probes are enabled by default.

Run the chart tests after installation:

```sh
helm test umbod
```

The tests verify API, MCP, and frontend health through their ClusterIP Services. They also verify RFC 9728 protected-resource metadata, OAuth authorization-server metadata, the MCP `WWW-Authenticate` discovery challenge, and that the running API loaded the selected installed plugins without exposing unselected plugins.

Run the same Docker-based Kind installation used by CI from `apps/umbod`:

```sh
deploy/helm/umbod/scripts/kind-install-test.sh
```

The script builds the core, frontend, and `ghcr.io/computerlovetech/umbod-plugins:ci` plugin images, creates a Kubernetes 1.32 Kind cluster, loads the images, installs the chart with `ci/kind-values.yaml`, verifies both plugin init containers and validator output, and runs the Helm tests. Archive mode requires all three `--core-image-archive`, `--frontend-image-archive`, and `--plugin-image-archive` arguments. It deletes the cluster afterward. Set `UMBOD_KIND_KEEP_CLUSTER=true` to retain the cluster for investigation.

## Validation

Run the validation script from any directory:

```sh
apps/umbod/deploy/helm/umbod/scripts/validate.sh
```

The script runs strict Helm linting, renders the chart with the CI values, validates the Kubernetes resources with kubeconform and the chart-specific validator, and verifies that the chart can be packaged. Temporary rendered and packaged artifacts are removed automatically.

CI runs three independent Helm jobs. Chart validation lints, renders, checks architecture, and packages the chart. Schema validation runs kubeconform against Kubernetes 1.25, the chart's minimum supported version, and Kubernetes 1.32, 1.33, and 1.34. Installation validation invokes `scripts/kind-install-test.sh` with the CI-built core, frontend, and plugin image archives. The same script performs local and CI cluster creation, image loading, chart installation, workload waiting, Helm tests, diagnostics, and cleanup.
