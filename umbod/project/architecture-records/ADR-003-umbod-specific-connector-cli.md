# ADR-003: Umbod-Specific Connector Development CLI

- **Status:** Accepted
- **Scope:** Connector developer experience in the Umbod SDK CLI
- **Implementation status:** Not implemented by this ADR
- **Date:** Not recorded

## Decision

The Umbod SDK CLI will add functionality specific to Umbod. It will not replace or wrap general-purpose tools such as uv, Docker, or Helm.

The admission criterion for a command is:

> Does this implement Umbod-specific knowledge, or merely hide another tool's command?

Retain the existing image-based connector delivery mechanism. Improve scaffolding, compatibility diagnostics, and validation without introducing bundle uploads or changing the connector execution model.

The [supporting detail](supporting/connector-cli.md) preserves the accepted constraints and verification requirements that accompany this decision.

## Context and rationale

Building a connector currently requires developers to assemble Python package metadata, connector code, image packaging, and deployment configuration. The SDK CLI can reduce errors and repetitive work by providing knowledge specific to Umbod.

New releases synchronize the SDK and container images (`bN` on PyPI corresponds to `-beta.N` on images), while Helm chart versions remain independent. Older artifacts released separately are not guaranteed to correspond. Developers still need compatibility guidance: matching declared versions do not establish runtime compatibility.

We considered simplifying delivery through uploaded connector bundles and adding CLI commands that orchestrate dependency resolution, image builds, publishing, and deployment. Neither is necessary to improve the initial developer experience. Existing tools already own those responsibilities.

## Alternatives considered

### CLI orchestration of uv, Docker, and Helm

Rejected. It hides standard tool behavior, duplicates interfaces, and expands the SDK into package management and deployment orchestration.

### Uploaded bundles managed by Umbod

Deferred. This requires artifact storage, approval, distribution to workers, coordinated activation, and rollback. It changes delivery rather than addressing the immediate documentation and development friction.

### Separate connector services

Deferred. Process isolation can address dependency conflicts and independent deployment, but requires a separate runtime and communication design. It is not necessary for this CLI improvement.

### Documentation-only improvements

Useful but insufficient on their own. Documentation remains the workflow guide; connector-specific scaffolding and executable checks reduce repetitive setup and detect mistakes that prose cannot.

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

## Confidence and reevaluation

Confidence and decision date were not recorded. Exact command names and compatibility metadata remain unresolved in the recorded design. Reevaluate through a new ADR if image delivery, dependency isolation, or the boundary with general-purpose tools changes. Acceptance does not establish implementation or successful validation.

## Supporting material

- [Accepted constraints and supporting detail](supporting/connector-cli.md)

- [Build a connector](../../docs/plugins/build-a-connector.md)
- [Umbod Connector SDK](../../../packages/umbod-sdk/README.md)
- [Release workflow](../../../.github/workflows/umbod-release.yml)
