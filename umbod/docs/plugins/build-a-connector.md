# Build a connector

Build connector distributions with the versioned Umbod connector-builder image. The image provides Python, `uv`, and the Connector SDK that matches the corresponding Umbod release.

## Requirements

- Docker
- Access to an OCI registry where you can push a plugin image
- Helm 3 and `kubectl`
- An Umbod `0.0.1-beta.2` installation

Set the Umbod release and the destination for your plugin image:

```bash
export UMBOD_RELEASE=0.0.1-beta.2
export UMBOD_CONNECTOR_BUILDER=ghcr.io/computerlovetech/umbod-connector-builder:$UMBOD_RELEASE
export PLUGIN_IMAGE=registry.example.com/your-organization/my-umbod-connector:0.1.0
```

Use the same release for the connector-builder image, core image, and Helm chart. Use immutable image tags rather than floating tags.

## Create the Python distribution

A connector is a standard Python distribution. Its `pyproject.toml` must:

- require Python 3.14 or newer;
- depend on a compatible `umbod` version;
- map that SDK dependency to `/opt/umbod-connector-sdk` for builds in the base image;
- declare each connector in the `umbod.connectors` entry-point group;
- configure the chosen Python build backend to include the connector package.

The builder image contains the SDK source at `/opt/umbod-connector-sdk`, so dependency resolution does not require a separately published Python package.

Declare the SDK source and connector entry point in `pyproject.toml`:

```toml
[project]
name = "my-umbod-connector"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
  "umbod>=0.1.0,<0.2.0",
]

[project.entry-points."umbod.connectors"]
my-connector = "my_umbod_connector:plugin"

[tool.uv.sources]
umbod = { path = "/opt/umbod-connector-sdk" }

[build-system]
requires = ["hatchling>=1.27.0,<2"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/my_umbod_connector"]
```

Generate or refresh the lock file inside the builder image:

```bash
docker run --rm \
  --user "$(id -u):$(id -g)" \
  --env HOME=/tmp \
  --volume "$PWD:/workspace" \
  "$UMBOD_CONNECTOR_BUILDER" \
  uv lock
```

Connector code imports the public contracts from `umbod_sdk.connectors.plugin_api`. The object named by an entry point must implement the Connector SDK plugin contract. Keep the entry-point name, connector definition ID, and Helm availability ID identical.

## Write a Hello World connector with the SDK

The `umbod` Python package provides the public Connector SDK under `umbod_sdk.connectors`. Use `umbod_sdk.connectors.plugin_api` for `Connector` and `ConfigurationCheckResult`, and subclass `umbod_sdk.connectors.proxies.Model` for the administrator configuration. The builder image supplies the SDK version matching your Umbod release.

For a minimal connector, create `src/my_umbod_connector/__init__.py` and export an object named `plugin`, matching the `my_umbod_connector:plugin` entry point above:

1. Define an empty administrator configuration model derived from `Model`, with extra fields forbidden. Hello World needs no credentials or external service.
2. Create a `Connector` with ID `my-connector`, name `Hello World`, a short description, and that configuration model. Assign it to `plugin`.
3. Register a configuration check on the connector that accepts the configuration model and returns `ConfigurationCheckResult.valid()`. It does not need to contact an external service.
4. Register a tool named `say_hello` on the connector with a plain-language description. Give it a `name` input with an `Annotated[str, Field(description=...)]` type and a `configuration` parameter typed as your configuration model. Return a greeting containing the supplied name. Umbod injects `configuration`; the agent supplies only `name`.

The ID `my-connector` must also appear in `plugins.availableConnectorIds` when you deploy. The entry-point name, connector ID, and Helm availability ID should match. Build and validate the image using the steps below; validation checks that Umbod can load the plugin, not that a tool call succeeds. After deployment, configure, publish, activate `say_hello`, and grant access to the calling agent's group as described at the end of this guide.

For connectors that call an external API, put credentials in the configuration model as `SecretStr`, perform a safe live configuration check, and keep HTTP requests in a separate client module. The [Connector SDK distribution guide](https://github.com/computerlovetech/umbod/tree/main/packages/umbod-sdk) covers entry points and distribution details.

## Create the plugin image

Use the connector-builder image as the build stage. Export third-party runtime dependencies without the SDK, install them into `/plugin-bundle`, then install the connector wheel without dependency resolution.

```dockerfile
ARG UMBOD_RELEASE=0.0.1-beta.2
FROM ghcr.io/computerlovetech/umbod-connector-builder:${UMBOD_RELEASE} AS builder

WORKDIR /workspace

COPY pyproject.toml uv.lock ./
RUN uv export \
      --frozen \
      --no-dev \
      --no-emit-project \
      --no-emit-package umbod \
      --output-file /tmp/runtime-requirements.txt \
    && uv pip install \
      --target /plugin-bundle \
      --requirements /tmp/runtime-requirements.txt

COPY . .
RUN uv build --wheel --out-dir /tmp/plugin-wheel \
    && uv pip install \
      --target /plugin-bundle \
      --no-deps \
      /tmp/plugin-wheel/*.whl \
    && test ! -e /plugin-bundle/umbod_sdk

FROM alpine:3.23

COPY --from=builder /plugin-bundle /plugin-bundle

ENTRYPOINT ["sh", "-c", "cp -R /plugin-bundle/. /plugins/"]
```

The resulting bundle contains connector code, Python distribution metadata, and third-party runtime dependencies. It does not contain the Connector SDK; Umbod core supplies the authoritative SDK at runtime.

Build and push the image:

```bash
docker build \
  --build-arg UMBOD_RELEASE="$UMBOD_RELEASE" \
  --tag "$PLUGIN_IMAGE" \
  .

docker push "$PLUGIN_IMAGE"
```

The registry must be reachable from the Kubernetes cluster. Configure Kubernetes image-pull credentials when using a private registry.

## Validate locally

Materialize the bundle and validate it with the matching core image:

```bash
mkdir -p .umbod-plugin-bundle

docker run --rm \
  --volume "$PWD/.umbod-plugin-bundle:/plugins" \
  "$PLUGIN_IMAGE"

docker run --rm \
  --volume "$PWD/.umbod-plugin-bundle:/plugins:ro" \
  "ghcr.io/computerlovetech/umbod:$UMBOD_RELEASE" \
  umbod connectors validate --plugin-path /plugins
```

Validation imports connector code. Only validate plugin images you trust. Structural validation does not call external providers or verify live credentials.

## Install with Helm

Create `values.plugins.yaml`:

```yaml
plugins:
  image:
    repository: registry.example.com/your-organization/my-umbod-connector
    tag: 0.1.0
    pullPolicy: IfNotPresent
  availableConnectorIds:
    - my-connector
```

Upgrade the existing release:

```bash
helm upgrade --install umbod \
  oci://ghcr.io/computerlovetech/charts/umbod \
  --version "$UMBOD_RELEASE" \
  --values values.plugins.yaml \
  --reuse-values \
  --set-string core.image.tag="$UMBOD_RELEASE" \
  --set-string frontend.image.tag="$UMBOD_RELEASE" \
  --wait --timeout 5m
```

For a release installed in another namespace, add the same `--namespace` option used during installation.

Run the chart tests:

```bash
helm test umbod --logs --timeout 2m
```

## Diagnose startup failures

The core Pod starts only after plugin materialization and validation succeed:

```bash
kubectl get pods
kubectl describe pod -l app.kubernetes.io/component=core
kubectl logs -l app.kubernetes.io/component=core -c connector-plugins
kubectl logs -l app.kubernetes.io/component=core -c validate-connector-plugins
```

Typical failures include an unavailable image, an SDK version mismatch, missing distribution metadata, duplicate connector IDs, or an unavailable ID in `plugins.availableConnectorIds`.

## Configure and expose the connector

After the workloads become ready:

1. Open Umbod and go to **Connectors**.
2. Select **Add connector**, then select the new connector.
3. Supply its settings and check the configuration.
4. Save and publish the connector.
5. Open the connector, activate its required tools, prompts, and resources, then save the capability selection.
6. Grant the connector and required capabilities to the calling agent's group under **Group permissions**.

The connector is agent-facing only after it is installed, deployment-available, configured, published, activated, and authorized.
