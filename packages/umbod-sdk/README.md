# Umbod Connector SDK

Public Python connector authoring API and plugin discovery contract for Umbod.

## Package

The SDK is published to PyPI as `umbod` (`pip install umbod`) and exposes the `umbod_sdk.connectors` Python package. It contains the public contracts used to implement connector plugins, including `umbod_sdk.connectors.plugin_api`, configuration models, registration contracts, uploaded files, and plugin discovery.

The SDK wheel includes the connector-authoring skill at `umbod_sdk/skills/draft-agent-connector/` (`SKILL.md` and `REFERENCE.md`). The `umbod skills` CLI lists bundled skills and installs a named skill or all bundled skills into a selected harness. Claude uses `.claude/skills/`; Codex and the shared agents convention use `.agents/skills/`. Installations default to the current project, with options for a different project or the user's home directory. Existing skill directories require explicit replacement. The CLI does not install skills automatically.

The SDK's `umbod connectors check` command reads a connector project's `pyproject.toml` (the current directory by default, or the directory selected with `--project`) and checks that its `umbod.connectors` entry-point group is nonempty and has well-formed names and module/export targets. Without a version option, it stays offline and checks metadata syntax only.

Add `--target RELEASE` to check the declared `umbod` dependency against a synchronized image release. The CLI reads the SDK-version labels in the public core and connector-builder registry metadata, verifies that supported Linux platform images agree, and checks the version range. It downloads metadata, not image layers, and never invokes Docker. Older releases without these labels cannot be inferred from their tags: obtain their SDK version from the actual runtime and use `--sdk-version VERSION` for an offline declaration check. These options are mutually exclusive. Missing or inconsistent release metadata fails without a compatibility verdict.

Version checks require exactly one unconditional, version-constrained `umbod` requirement in static `[project].dependencies`. Dynamic dependencies, conditional SDK requirements, direct SDK URLs, duplicate SDK declarations, and optional-only SDK dependencies cannot be checked. Explicitly selected prerelease versions are evaluated against the declared range; successful checking does not change uv's dependency-resolution policy. No check imports connector code, changes files, checks connector ID consistency, or proves runtime loading or external-service compatibility. The core application's `connectors validate` remains the separate loading check for an installed plugin bundle.

`umbod connectors init --name my-connector --module my_package.hello_world [--project PATH] [--apply]` previews a complete Hello World connector module and the exact entry-point addition to `pyproject.toml`. Only `--apply` writes. It supports an existing Hatchling project with a `[project]` table, a `src/my_package/__init__.py`, and explicit Hatch wheel inclusion of `src/my_package`. The `--module` package and module names must each be ASCII Python identifiers (not keywords or `__init__`). It refuses existing connector entry-point groups, dynamic entry points, target collisions, and symlinked project paths; it does not edit build configuration, install dependencies, or load the generated connector. An interrupted `--apply` can leave a module and/or partial metadata addition; inspect both reported paths manually. It does not provide a two-file atomic transaction or automatically remove a created module after a metadata failure. Manage dependencies with uv yourself and run `umbod connectors check` afterward for metadata syntax checking; neither command establishes runtime compatibility.

Concrete connector implementations belong in separate Python distributions. Umbod discovers installed connector distributions through Python package entry points and enables a deployment-specific subset through its connector deployment configuration.

## Plugin system overview

Connector authors build Python distributions against this SDK. The distribution publishes each plugin through the `umbod.connectors` entry-point group and declares its runtime dependencies as normal Python package dependencies.

Connector implementations are distributed separately from the SDK. Docker packages each connector distribution and its dependencies for use by Umbod.

Discovery and availability are separate controls. Entry points identify installed implementations; the Helm deployment availability configuration selects which connector IDs an environment enables.

```mermaid
flowchart TB
    Author[Connector author]

    subgraph Authoring[Authoring and packaging]
        SDK[Umbod Connector SDK]
        Package[Connector plugin package<br/>Dinero · Rejseplanen · Slack · test]
        EntryPoints[Python entry points<br/>Plugin discovery metadata]
        Dependencies[Plugin dependencies]

        Package -->|uses| SDK
        Package --> EntryPoints
        Package --> Dependencies
    end

    Author -->|builds with| SDK

    subgraph Deployment[Docker deployment]
        PluginBundle[Packaged plugins and dependencies]
        Availability[Deployment configuration<br/>Enabled connector IDs]

        EntryPoints --> PluginBundle
        Dependencies --> PluginBundle
    end

    subgraph Core[Umbod]
        API[Core API<br/>Administration and configuration]
        MCP[MCP server<br/>Agent-facing capabilities]
        Store[(Umbod data)]

        PluginBundle --> API
        PluginBundle --> MCP
        Availability --> API
        Availability --> MCP
        API <--> Store
        MCP <--> Store
    end

    Frontend[Administration frontend] --> API
    Agent[MCP client or agent] --> MCP

    MCP -->|Dinero plugin| Dinero[Dinero API]
    MCP -->|Rejseplanen plugin| Rejseplanen[Rejseplanen API]
    MCP -->|Slack plugin| Slack[Slack API]
    MCP -->|test plugin| Test[Test connector]
```

The frontend obtains connector definitions and administration state through the core API. The MCP server discovers the enabled plugins and exposes their eligible capabilities to agents.

## Python runtime loading details

The core application and plugins are packaged separately, but they execute in the same Python interpreter. The core image provides the application virtual environment and the authoritative Connector SDK. The plugin image resolves each plugin package's declared dependencies into a separate bundle, which Docker makes available to both core processes.

```mermaid
flowchart LR
    subgraph CoreBuild[Core image build]
        CoreProject[Umbod core project]
        SDKWheel[Connector SDK]
        CoreVenv[Core virtual environment<br/>Umbod · SDK · core dependencies]

        CoreProject -->|installed into| CoreVenv
        SDKWheel -->|installed into| CoreVenv
    end

    subgraph PluginBuild[Plugin image build]
        PluginProject[Connector plugin package]
        PluginMetadata[Entry-point metadata<br/>umbod.connectors]
        PluginRequirements[Declared plugin dependencies<br/>such as httpx]
        PluginBundle[Plugin bundle<br/>Plugin code · metadata · dependencies]

        PluginProject --> PluginMetadata
        PluginProject --> PluginRequirements
        PluginProject -->|installed into| PluginBundle
        PluginMetadata --> PluginBundle
        PluginRequirements -->|resolved and installed| PluginBundle
    end

    SDKBuildCopy[SDK build-time copy] -->|validates plugin installation| PluginBundle
    PluginBundle -->|SDK copy removed after build| BundledWithoutSDK[Deployable plugin bundle]

    subgraph Runtime[API or MCP Python process]
        Interpreter[Python interpreter<br/>from the core virtual environment]
        ImportPaths[Combined import locations<br/>core environment and plugin bundle]
        Discovery[importlib.metadata<br/>loads connector entry points]
        LoadedPlugin[Loaded connector plugin]
        LoadedDependencies[Imported plugin dependencies]
        CoreSDK[Connector SDK from core environment]

        Interpreter --> ImportPaths
        ImportPaths --> Discovery
        Discovery --> LoadedPlugin
        ImportPaths --> LoadedDependencies
        LoadedPlugin --> CoreSDK
        LoadedPlugin --> LoadedDependencies
    end

    CoreVenv --> Interpreter
    CoreVenv --> ImportPaths
    BundledWithoutSDK --> ImportPaths
```

There is no virtual environment per connector. The API process loads plugins into the API interpreter, and the MCP process loads plugins into the MCP interpreter. Within either process, all enabled plugins share one module namespace and dependency resolution context. Declaring a dependency in a plugin package ensures it is carried in the plugin bundle, but it does not isolate that dependency from core dependencies or dependencies declared by other plugins. Plugins that require mutually incompatible versions need a process or container boundary rather than additional in-process virtual environments.

## Creating a connector distribution

A connector distribution must:

1. Depend on a compatible `umbod` version.
2. Implement a connector using the public `umbod_sdk.connectors.plugin_api` interface.
3. Export the connector plugin object from an importable module.
4. Declare that exported object in the `umbod.connectors` entry-point group.
5. Be installed in the Python environment or plugin bundle used by Umbod.
6. Be enabled by connector ID in the deployment configuration.

A typical distribution layout is:

```text
my-umbod-connectors/
├── pyproject.toml
└── src/
    └── my_umbod_connectors/
        └── my_service/
            ├── __init__.py
            ├── admin_configuration.py
            ├── api_client.py
            └── configuration_check.py
```

The public [connector authoring guide](https://umbod.ai/docs/plugins/build-a-connector/) describes the supported image build and deployment workflow.

## Declaring plugin discovery metadata

Use the standardized Python package entry-point metadata in the connector distribution's `pyproject.toml`:

```toml
[project]
name = "my-umbod-connectors"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "umbod>=0.1.0,<0.2.0",
]

[project.entry-points."umbod.connectors"]
my-service = "my_umbod_connectors.my_service:MyServiceConnectorPlugin"
```

Each entry has three parts:

- `my-service` is the entry-point name recorded in package metadata.
- `my_umbod_connectors.my_service` is the importable Python module.
- `MyServiceConnectorPlugin` is the plugin object exported by that module.

Umbod loads entries from the `umbod.connectors` group with `importlib.metadata`. An entry may resolve directly to a connector plugin object or to a callable that returns one.

The entry-point name identifies the package metadata entry, but deployment selection uses the ID declared by the loaded connector:

```python
connector = Connector(
    id="my-service",
    name="My Service",
    description="Connects agents to My Service.",
    configuration=MyServiceAdminConfiguration,
)

MyServiceConnectorPlugin = connector
```

Keep the entry-point name, `Connector.id`, and deployment configuration ID identical. Although discovery ultimately indexes the loaded plugin by `Connector.id`, using one stable identifier prevents ambiguity across packaging and deployment configuration. Connector IDs must be unique across all installed plugins.

## Enabling an installed connector

Installing a connector distribution makes its plugin discoverable; it does not automatically make the connector available in a deployment. The deployment configuration must also include its `Connector.id`:

```json
{
  "connectors": [
    {
      "id": "my-service"
    }
  ]
}
```

The Helm chart renders this availability configuration from `plugins.availableConnectorIds`.

The distinction is intentional:

- Entry-point metadata declares which connector implementations are installed and discoverable.
- Deployment configuration declares which discovered connectors are enabled in that environment.
- A discovered connector omitted from deployment configuration remains disabled.
- An enabled connector whose plugin is not discoverable causes startup validation to fail.

## Building and verifying the distribution

Use the versioned `ghcr.io/computerlovetech/umbod-connector-builder` image to lock dependencies and build the connector distribution. The image contains Python, `uv`, and the matching SDK. Package connector code, distribution metadata, and third-party runtime dependencies into the plugin bundle without copying the SDK. The matching Umbod core image validates the completed bundle before deployment.

## Directory-based development plugins

Umbod can also discover Python files from the directory selected by `UMBOD_CONNECTOR_PLUGIN_DIR`. Each non-private `.py` file may expose `plugin`, a `plugins` list, or plugin-shaped module values. This mechanism is intended for development and externally mounted plugin files. Installable connector distributions should use package entry points because entry points preserve package ownership, dependencies, versioning, and standard Python installation behavior.

## Package boundary

This SDK distribution contains connector authoring and discovery contracts and the connector-authoring skill. Concrete connector implementations are distributed separately, such as the repository's `umbod-connectors` package.
