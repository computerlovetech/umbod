# Build a connector

The Umbod SDK CLI can generate a working Hello World connector and check its package metadata before you build an image. You no longer need to write the starter module or entry point by hand. The versioned connector-builder image supplies Python, `uv`, and the SDK used by the corresponding Umbod core image.

The short path is: create a Hatch project with `uv`, run `umbod connectors init` (preview, then `--apply`), run `umbod connectors check`, build and validate a plugin image, and enable it in Helm. The CLI does not build or deploy the image for you.

## Requirements

- Python 3.14 or newer and `uv`
- An Umbod SDK CLI release containing `connectors init` and `connectors check` (installed below)
- Docker
- Access to an OCI registry where you can push a plugin image
- Helm 3 and `kubectl`
- An Umbod installation and a published connector-builder and core image for the same release

Set the image and chart versions and the destination for your plugin image. The beta.4 tags below are an example; substitute the published release you are running:

```bash
export UMBOD_RELEASE=0.0.1-beta.4
export UMBOD_CHART_VERSION=0.0.1-beta.4
export UMBOD_CONNECTOR_BUILDER=ghcr.io/computerlovetech/umbod-connector-builder:$UMBOD_RELEASE
export PLUGIN_IMAGE=registry.example.com/your-organization/my-umbod-connector:0.1.0
```

Use the same immutable tag for the connector-builder, core, and frontend images. Select a published Helm chart version separately; its version need not match the image tag. New releases publish the SDK and image group together: a `-beta.N` image tag corresponds to a `bN` PyPI SDK version (stable versions have the same spelling). Older, independently released artifacts are not retroactively guaranteed to match. Helm chart versions remain independent, so do not assume a chart exists with the image tag. The builder image contains the SDK source used by the core image; choose a compatible `umbod` dependency range in `pyproject.toml` that includes that SDK version. Check the selected builder image's SDK version before locking dependencies, and validate the bundle against the selected core image.

## Create the Python distribution

Install the SDK CLI in its own tool environment and create a Python project with uv:

```bash
uv tool install --python 3.14 --prerelease allow umbod
uv init --lib --build-backend hatch --python 3.14 my-umbod-connector
cd my-umbod-connector
```

If the SDK tool is already installed, use `uv tool upgrade --prerelease allow umbod`. The prerelease option allows installation of the CLI while it is distributed in beta releases. Keep this tool environment separate from the connector's build environment: the latter resolves the SDK from the builder image, not from PyPI.

Configure `pyproject.toml` as below. Choose an `umbod` dependency range that includes the SDK in your selected release. For a beta SDK, explicitly include its beta version in the lower bound. You can read the exact version from the builder image with the command in the [older-release fallback](#older-release-fallback) below. Keep any other project metadata and dependencies you need. The builder image contains the SDK source at `/opt/umbod-connector-sdk`, so builds do not require that SDK version to be published separately on PyPI.

Do not add the connector entry-point table yet; `init` adds it:

```toml
[project]
name = "my-umbod-connector"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
  "umbod>=0.1.0,<0.2.0",
]

[tool.uv.sources]
umbod = { path = "/opt/umbod-connector-sdk" }

[build-system]
requires = ["hatchling>=1.27.0,<2"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/my_umbod_connector"]
```

## Initialize and check the connector

From the project directory, preview the generated Hello World module and entry-point metadata, then explicitly apply them:

```bash
umbod connectors init --name my-connector --module my_umbod_connector.hello_world
umbod connectors init --name my-connector --module my_umbod_connector.hello_world --apply
```

`init` requires the existing `src/my_umbod_connector/__init__.py` created by uv and explicit Hatch wheel package inclusion as shown above. It refuses existing connector entry-point groups, destination modules, and symlinked paths. It does not install dependencies, change lockfiles, or overwrite files. If apply reports a partial write, inspect the named files before retrying.

Check entry-point syntax locally:

```bash
umbod connectors check
```

This command is offline and does not import the connector. If you substituted a newer synchronized image release with SDK-version labels, check its declared SDK dependency as well:

```bash
umbod connectors check --target "$UMBOD_RELEASE"
```

`--target` reads core and builder image registry metadata, checks that their SDK versions agree, and verifies that the version satisfies your declared `umbod` dependency. It does not pull image layers, run Docker, or import the connector. The example `0.0.1-beta.4` predates those labels, so use the fallback below if you kept that tag.

### Older-release fallback

For an older image release without SDK-version labels, read the SDK version from the selected builder image and check it explicitly:

```bash
export UMBOD_SDK_VERSION="$(docker run --rm "$UMBOD_CONNECTOR_BUILDER" \
  python -c 'from importlib.metadata import version; print(version("umbod"))')"
umbod connectors check --sdk-version "$UMBOD_SDK_VERSION"
```

`--sdk-version` is an offline declaration check, not image verification. Do not infer the SDK version from an old image tag. `--target` and `--sdk-version` cannot be combined. Neither mode proves runtime loading or external-service compatibility; validate the completed bundle with the core image below. If the check fails, adjust the `umbod` dependency range in `pyproject.toml` to include the actual SDK version and rerun it.

Generate or refresh the lock file using uv inside the builder image:

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

`init --apply` creates `src/my_umbod_connector/hello_world.py` and adds `[project.entry-points."umbod.connectors"]` to `pyproject.toml`. No manual entry-point edit is needed. The generated module is a working Hello World connector; inspect and extend it when you need additional capabilities:

```python
from typing import Annotated

from pydantic import ConfigDict, Field
from umbod_sdk.connectors.plugin_api import ConfigurationCheckResult, Connector
from umbod_sdk.connectors.proxies import Model


class HelloWorldConfiguration(Model):
    model_config = ConfigDict(extra="forbid")


connector = Connector(
    id="my-connector",
    name="My Connector",
    description="Greets people with a hello world message.",
    capability_description="Say hello to a person.",
    configuration=HelloWorldConfiguration,
)


@connector.configuration_check
def check_configuration(configuration: HelloWorldConfiguration) -> ConfigurationCheckResult:
    return ConfigurationCheckResult.valid()


@connector.tool(description="Greet a person by name.")
def say_hello(
    name: Annotated[str, Field(description="Name of the person to greet.")],
    configuration: HelloWorldConfiguration,
) -> str:
    return f"Hello, {name}!"


plugin = connector
```

The `plugin` object matches the `my_umbod_connector.hello_world:plugin` entry point added by `init`. Umbod injects `configuration`; the agent supplies only `name`. The `my-connector` ID also matches `plugins.availableConnectorIds` in the Helm values below. Build and validate the image using the next steps. After deployment, configure, publish, activate `say_hello`, and grant access to the calling agent's group.

For connectors that call an external API, put credentials in the configuration model as `SecretStr`, perform a safe live configuration check, and keep HTTP requests in a separate client module. The [Connector SDK distribution guide](https://github.com/computerlovetech/umbod/tree/main/packages/umbod-sdk) covers entry points and distribution details.

If you use an AI coding agent, the SDK also bundles a connector-authoring skill. Run `umbod skills list` to see bundled skills, then, from your connector project, run `umbod skills install draft-agent-connector --harness agents` (or `--harness claude` / `--harness codex`). This installs guidance under `.agents/skills/` (or `.claude/skills/`) for your agent; it does not create a connector, install dependencies, or deploy anything. Use `--scope user` for a user-wide installation, `--project PATH` to target another project, or `--force` to replace an existing skill.

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
