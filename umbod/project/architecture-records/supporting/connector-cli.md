# Umbod-Specific Connector Development CLI — supporting detail

Preserved from [ADR-003: Umbod-Specific Connector Development CLI](../ADR-003-umbod-specific-connector-cli.md). These details remain part of the accepted record; relocation does not change their authority or claim that implementation or verification is complete.

## Responsibility Boundaries

| Tool | Responsibility |
| --- | --- |
| uv | Python project management, dependencies, environments, locking, and Python distribution builds |
| Docker | Container image builds, local container execution, and registry pushes |
| Helm | Kubernetes installation, deployment configuration, and upgrades |
| Umbod SDK CLI | Connector scaffolding, connector metadata checks, SDK compatibility checks, and connector contract validation |

The SDK CLI must not invoke these tools as a hidden workflow or forward their options through an Umbod command. Documentation may describe their commands directly. Generated packaging files may use them explicitly.

External metadata access for Umbod compatibility checks is permitted; this does not make the CLI a package manager or deployment tool. Such access should use explicit ports and adapters rather than shelling out to another CLI.

## Intended Capabilities

### Connector initialization

Add connector-specific files and entry-point metadata to an existing Python project. Initialization may generate packaging files for the supported image delivery workflow.

Initialization must show intended changes and must not silently overwrite existing files. It must not initialize a replacement Python environment, install dependencies, or resolve a lock file. Missing prerequisites should produce guidance for the tool that owns them.

### Connector checks

Check connector metadata, entry-point declarations, identifier consistency, and compatibility with an explicitly selected target Umbod release.

Checks are read-only. They must not rewrite dependencies, refresh locks, select a newer target, or upgrade a deployment. Diagnostics should identify the failed check and an actionable next step.

SDK compatibility must be assessed against the SDK supplied by the target runtime, not by treating matching PyPI SDK and image versions as runtime validation. New builder and core images use the synchronized SDK release; the Helm chart version is selected independently.

If required compatibility information is unavailable, report that the check could not establish compatibility rather than treating matching version strings as proof.

### Connector loading validation

Validate connector discovery and the public plugin contract in the environment where the validation command runs. Reuse the existing validation behavior where appropriate instead of introducing competing validation rules.

The CLI does not launch Docker to create that environment. Developers explicitly use the supported builder or core image when target-runtime validation is required. Validation in a local environment must not be presented as proof of compatibility with a different runtime.

Loading a connector executes Python code. Only trusted connectors should be validated. Structural validation does not invoke external connector tools or establish that credentials and upstream services work.

## Command Surface

Initialization, checking, and validation are the intended connector capabilities. Exact command names, flags, and placement must be reconciled with the existing SDK and application CLI before implementation.

Do not add connector build, lock, publish, or deploy commands merely to wrap uv, Docker, or Helm. A future command with one of those names would require a distinct Umbod-specific responsibility and a separate design decision.

## Delivery and Runtime Constraints

Connector distributions and their third-party dependencies continue to be packaged in plugin images. The plugin bundle excludes the SDK, which Umbod core supplies at runtime.

This decision does not introduce per-connector dependency isolation. In-process connectors continue to share the core Python environment and must coexist with its dependencies and those of other connectors. Native dependencies must match the target runtime platform.

Registry credentials, image publication, cluster access, and rollout remain responsibilities of the existing delivery tools and operational workflow.

## Implementation Acceptance Criteria

- Connector commands do not invoke uv, Docker, or Helm.
- Initialization preserves existing user files unless replacement is explicitly authorized.
- Checks do not mutate project files or deployment state.
- Compatibility checks distinguish SDK, image, and chart versions.
- Validation identifies its execution environment and does not imply unperformed target-runtime or live-service verification.
- Documentation uses the standard tools directly for dependency management, image builds, publication, and deployment.
- Existing image delivery remains supported without requiring an upload service.
