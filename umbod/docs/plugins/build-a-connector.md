# Build a connector

Build connector distributions with the versioned Umbod connector-builder image. The image provides Python, `uv`, and the Connector SDK used by the corresponding Umbod core image.

## Requirements

- Docker
- Access to an OCI registry where you can push a plugin image
- Helm 3 and `kubectl`
- An Umbod `0.0.1-beta.4` installation

Set the image and chart versions and the destination for your plugin image:

```bash
export UMBOD_RELEASE=0.0.1-beta.4
export UMBOD_CHART_VERSION=0.0.1-beta.4
export UMBOD_CONNECTOR_BUILDER=ghcr.io/computerlovetech/umbod-connector-builder:$UMBOD_RELEASE
export PLUGIN_IMAGE=registry.example.com/your-organization/my-umbod-connector:0.1.0
```

Use the same immutable tag for the connector-builder, core, and frontend images. Select a published Helm chart version separately; its version need not match the image tag. The release pipeline versions the SDK on PyPI, the image group, and the Helm chart independently, so do not assume that a PyPI SDK release exists with the image tag (or that a chart with that version exists). The builder image contains the SDK source used by the core image; choose a compatible `umbod` dependency range in `pyproject.toml` that includes that SDK version. Check the selected builder image's SDK version before locking dependencies, and validate the bundle against the selected core image.

## Create the Python distribution

A connector is a standard Python distribution. Its `pyproject.toml` must:

- require Python 3.14 or newer;
- depend on a compatible `umbod` version;
- map that SDK dependency to `/opt/umbod-connector-sdk` for builds in the base image;
- declare each connector in the `umbod.connectors` entry-point group;
- configure the chosen Python build backend to include the connector package.

The builder image contains the SDK source at `/opt/umbod-connector-sdk`, so dependency resolution does not require a separately published Python package. The dependency range below is illustrative; adjust it to include the SDK version in your chosen builder image.

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

Create `src/my_umbod_connector/__init__.py` with a complete Hello World connector:

```python
from typing import Annotated

from pydantic import ConfigDict, Field
from umbod_sdk.connectors.plugin_api import ConfigurationCheckResult, Connector
from umbod_sdk.connectors.proxies import Model


class HelloWorldConfiguration(Model):
    model_config = ConfigDict(extra="forbid")


plugin = Connector(
    id="my-connector",
    name="Hello World",
    description="Greets people by name.",
    capability_description="Say hello to someone.",
    configuration=HelloWorldConfiguration,
)


@plugin.configuration_check
def check_configuration(configuration: HelloWorldConfiguration) -> ConfigurationCheckResult:
    return ConfigurationCheckResult.valid()


@plugin.tool(description="Greet someone by name.")
def say_hello(
    name: Annotated[str, Field(description="Name of the person to greet.")],
    configuration: HelloWorldConfiguration,
) -> str:
    return f"Hello, {name}!"
```

The `plugin` object matches the `my_umbod_connector:plugin` entry point above. Umbod injects `configuration`; the agent supplies only `name`. The `my-connector` ID also matches `plugins.availableConnectorIds` in the Helm values below. Build and validate the image using the next steps. After deployment, configure, publish, activate `say_hello`, and grant access to the calling agent's group.

For connectors that call an external API, put credentials in the configuration model as `SecretStr`, perform a safe live configuration check, and keep HTTP requests in a separate client module. The [Connector SDK distribution guide](https://github.com/computerlovetech/umbod/tree/main/packages/umbod-sdk) covers entry points and distribution details.

## Create the plugin image

Use the connector-builder image as the build stage. Export third-party runtime dependencies without the SDK, install them into `/plugin-bundle`, then install the connector wheel without dependency resolution.

```dockerfile
ARG UMBOD_RELEASE=0.0.1-beta.4
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
  --version "$UMBOD_CHART_VERSION" \
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
