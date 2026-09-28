# ADR-003: Umbod-Specific Connector Development CLI

- **Status:** Accepted
- **Scope:** Connector developer experience in the Umbod SDK CLI
- **Implementation status:** Not implemented by this ADR

## Context

Building a connector currently requires developers to assemble Python package metadata, connector code, image packaging, and deployment configuration. The SDK CLI can reduce errors and repetitive work by providing knowledge specific to Umbod.

The SDK, container images, and Helm chart are versioned and released independently. Developers need compatibility guidance, not an assumption that all artifacts share a version number.

We considered simplifying delivery through uploaded connector bundles and adding CLI commands that orchestrate dependency resolution, image builds, publishing, and deployment. Neither is necessary to improve the initial developer experience. Existing tools already own those responsibilities.

## Decision

The Umbod SDK CLI will add functionality specific to Umbod. It will not replace or wrap general-purpose tools such as uv, Docker, or Helm.

The admission criterion for a command is:

> Does this implement Umbod-specific knowledge, or merely hide another tool's command?

Retain the existing image-based connector delivery mechanism. Improve scaffolding, compatibility diagnostics, and validation without introducing bundle uploads or changing the connector execution model.

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

SDK compatibility must be assessed against the SDK supplied by the target runtime, not by comparing the PyPI SDK version with an image tag. Builder and core images use the same image release; the Helm chart version is selected independently.

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

## Consequences

### Positive

- Developers receive targeted guidance for Umbod concepts without learning a second interface to familiar tools.
- Standard Python, container, and deployment workflows remain usable locally and in CI.
- The SDK avoids maintaining wrappers, credential handling, and orchestration for external tools.
- Compatibility failures can be detected earlier without silently changing the project or deployment.
- Delivery and runtime architecture remain unchanged.

### Trade-offs

- Developers still need to understand and run uv, Docker, and Helm where applicable.
- The workflow is not a single end-to-end command.
- Generated files and compatibility checks must evolve with the supported SDK and runtime contracts.
- Documentation must clearly distinguish local checks from validation in the actual target environment.

## Alternatives Considered

### CLI orchestration of uv, Docker, and Helm

Rejected. It hides standard tool behavior, duplicates interfaces, and expands the SDK into package management and deployment orchestration.

### Uploaded bundles managed by Umbod

Deferred. This requires artifact storage, approval, distribution to workers, coordinated activation, and rollback. It changes delivery rather than addressing the immediate documentation and development friction.

### Separate connector services

Deferred. Process isolation can address dependency conflicts and independent deployment, but requires a separate runtime and communication design. It is not necessary for this CLI improvement.

### Documentation-only improvements

Useful but insufficient on their own. Documentation remains the workflow guide; connector-specific scaffolding and executable checks reduce repetitive setup and detect mistakes that prose cannot.

## Implementation Acceptance Criteria

- Connector commands do not invoke uv, Docker, or Helm.
- Initialization preserves existing user files unless replacement is explicitly authorized.
- Checks do not mutate project files or deployment state.
- Compatibility checks distinguish SDK, image, and chart versions.
- Validation identifies its execution environment and does not imply unperformed target-runtime or live-service verification.
- Documentation uses the standard tools directly for dependency management, image builds, publication, and deployment.
- Existing image delivery remains supported without requiring an upload service.

## References

- [Build a connector](../../docs/plugins/build-a-connector.md)
- [Umbod Connector SDK](../../../packages/umbod-sdk/README.md)
- [Release workflow](../../../.github/workflows/umbod-release.yml)
