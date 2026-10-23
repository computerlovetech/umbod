# Umbod Website Context

## Purpose

Umbod is one self-hosted, open-source platform for connecting internal APIs and MCP
servers, managing group access, and using compatible agents on Kubernetes.

- `/` introduces the platform and leads with Get started at `/#how`.
- `/#how` provides a local kind cluster evaluation walkthrough and links to the
  full installation guide.
- `/enterprise/` remains a working platform entry with the same onboarding.
- Legacy `/download` and `/download/` links redirect to `/#how`.

Shared navigation includes Docs and Get started; the duplicate Enterprise page is
not linked in navigation. Get started always returns to `/#how`, including mobile
and JavaScript-disabled navigation. Contact
is the secondary conversion path; visitors should not need to contact us to try
the platform.

## Product boundaries

Lead with connectors, group permissions, Kubernetes deployment and the platform
walkthrough. Keep documentation accessible and distinguish current beta
capabilities from future plans. The current chart uses a single core replica
backed by SQLite and is for evaluation, not a claim of production readiness.

Do not advertise native app downloads, separate product editions, automatic
configuration migration, pricing tiers, invented customers, compliance guarantees
or unshipped operational capabilities.

Build navigation, metadata and primary content into each HTML entry so direct
links and JavaScript-disabled visits work. Keep release versions sourced from the
repository-root `release-metadata.json`.

## Visual direction and voice

Preserve the restrained, spacious layout, light background, green accents, logo
and typography. Use product evidence such as the architecture diagram and
Kubernetes walkthrough. Favor a direct developer voice, transparent technical
boundaries, clear documentation and visible community destinations. Defer mascot
branding until after launch and further public product iterations.

Reference projects include T3 Code, Unsloth, Caveman, Ollama and Orca for
product-first demonstration, approachable education, explicit limits, simple
onboarding and community distribution. Borrow principles, not unsupported claims
or another project's identity.

The detailed review and recommendations live in
`docs/research/open-source-reference-projects.md`.
