---
description: Write a custom Umbod connector in Python, package it as a plugin image, and install it with Helm.
---

# Build a connector

Write a connector in Python when an [OpenAPI or MCP connector](../use/connectors.md) is not enough. A connector is a Python package, shipped to Umbod in a container image called a plugin image. Custom connectors need a self-hosted Umbod.

Already have a plugin image? Skip to [Install the image](#5-install-the-image).

!!! warning "Plugins are trusted code"
    A plugin runs inside Umbod with full access to its files, network, and secrets. It is not sandboxed. Install only images you have reviewed.

## Before you start

- Python 3.14, [`uv`](https://docs.astral.sh/uv/), and Docker
- A container registry your cluster can pull from
- A [running Umbod](../self-host/install.md) on release `{{ release.imageTag }}`

Set these once. Every command below uses them:

```bash
export UMBOD_RELEASE={{ release.imageTag }}
export PLUGIN_IMAGE=registry.example.com/your-org/my-umbod-connector:0.1.0
```

Use the same release for the builder image, the Umbod images, and the chart. Image release `{{ release.imageTag }}` matches SDK `{{ release.sdkVersion }}` on PyPI.

## 1. Create the project

```bash
uv tool install --python 3.14 --prerelease allow umbod
uv init --lib --build-backend hatch --python 3.14 my-umbod-connector
cd my-umbod-connector
```

Replace the contents of `pyproject.toml`:

```toml
[project]
name = "my-umbod-connector"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
  "umbod>={{ release.sdkVersion }}",
]

[tool.uv.sources]
umbod = { path = "/opt/umbod-connector-sdk" }

[build-system]
requires = ["hatchling>=1.27.0,<2"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/my_umbod_connector"]
```

The SDK path exists inside the builder image, which is where the build runs.

## 2. Generate the connector

```bash
umbod connectors init --name my-connector --module my_umbod_connector.hello_world --apply
```

Without `--apply`, the command only previews. It creates `src/my_umbod_connector/hello_world.py` and adds the entry point to `pyproject.toml`:

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

Umbod passes in `configuration`. The agent supplies only `name`. For a connector that calls an API, put credentials in the configuration model as `SecretStr`.

The connector ID (`my-connector`) must be the same in the code, the entry point, and the Helm values in step 5.

**Check:**

```bash
umbod connectors check --target "$UMBOD_RELEASE"
```

This confirms the entry point and that your `umbod` dependency matches the release.

Working with a coding agent? `umbod skills install draft-agent-connector --harness agents` adds connector-writing guidance to your project. Use `--harness claude` or `--harness codex` for those agents.

## 3. Build the image

Create the lock file inside the builder image:

```bash
docker run --rm \
  --user "$(id -u):$(id -g)" \
  --env HOME=/tmp \
  --volume "$PWD:/workspace" \
  "ghcr.io/computerlovetech/umbod-connector-builder:$UMBOD_RELEASE" \
  uv lock
```

Create `Dockerfile`:

```dockerfile
ARG UMBOD_RELEASE={{ release.imageTag }}
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

The image holds your code and its dependencies, but not the SDK. Umbod supplies the SDK at runtime.

Build and push:

```bash
docker build --build-arg UMBOD_RELEASE="$UMBOD_RELEASE" --tag "$PLUGIN_IMAGE" .
docker push "$PLUGIN_IMAGE"
```

Use a fixed tag for every build. Tags such as `latest` are not supported.

## 4. Validate the image

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

**Check:** the second command exits with status `0`. It loads the connector the way Umbod will. It does not test credentials or call external services.

## 5. Install the image

Add to your values file:

```yaml
plugins:
  image:
    repository: registry.example.com/your-org/my-umbod-connector
    tag: 0.1.0
  availableConnectorIds:
    - my-connector
```

Then run the `helm upgrade --install` command from [Install](../self-host/install.md#4-install) again.

Only connectors listed in `availableConnectorIds` can be used. Umbod takes one plugin image, so put all your connectors in it.

**Check:** `helm -n umbod test umbod --logs --timeout 2m` passes.

## 6. Publish the connector

1. In **Administration → Connectors**, choose **Add connector**, then **Native connector**, and select your connector.
2. Fill in its settings and publish it.
3. Activate the tools you want to offer.
4. In **Administration → Permissions**, grant a group the connector and its tools.

**Check:** an agent signed in as a member of that group lists `say_hello`.

## If the Pod does not start

Umbod starts only after the plugin image has loaded and passed validation:

```bash
kubectl -n umbod logs -l app.kubernetes.io/component=core -c connector-plugins
kubectl -n umbod logs -l app.kubernetes.io/component=core -c validate-connector-plugins
```

| Log shows | Fix |
| --- | --- |
| Image cannot be pulled | Check the tag, the registry address, and the cluster's image-pull secret |
| SDK version mismatch | Build with the builder image of the same release as Umbod |
| Unknown connector ID | Every ID in `availableConnectorIds` must exist in the image |
| Duplicate connector ID | Two connectors in the image use the same ID |
