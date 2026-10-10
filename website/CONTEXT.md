# Umbod Website Context

## Purpose

The website has two conversion paths under one restrained Umbod identity:

- `/` introduces the native desktop app to individuals. Lead with the local MCP
  gateway, shared per-tool permissions across local clients, and desktop downloads.
  State availability, OS/architecture support and prerelease signing limits honestly.
  Do not present cluster installation, group administration or the platform video as
  desktop capabilities. A labeled connection diagram is preferable to a fake screenshot.
- `/enterprise/` introduces the self-hosted platform to platform teams. Keep the
  existing connectors, group permissions, Kubernetes walkthrough and beta limits here.
  Lead with contact and self-hosting docs, and retain the local cluster evaluation guide.

The shared navigation includes Docs, Enterprise and Download. Download always returns
to `/#downloads`. This follows Orca's separation of individual and enterprise journeys,
not its copy, visual identity, testimonials or unsupported product claims.

Keep documentation accessible and distinguish current beta capabilities from future
plans. Avoid pricing tiers, invented customers, compliance claims and promises of
production readiness. Build navigation, metadata and primary content into each HTML
entry so direct links and JavaScript-disabled visits work.

## Product strategy

Umbod has two deliberately connected products:

- **Local Umbod is the distribution and community product.** It should be genuinely useful to an
  individual, easy to run across developer platforms, and capable of creating users, ambassadors,
  connector authors, policy authors, and community knowledge. It is not merely a limited enterprise
  trial.
- **Enterprise Umbod is the operational and revenue product.** It manages shared
  connectors and group access in cloud-native environments, with organizational
  authentication and administration. Reliability, compliance, support and managed
  operations are longer-term product goals, not present-day guarantees.

Portability is a product direction, not a shipped capability. Today Desktop uses a
Rust gateway with native SwiftUI/WPF interfaces, while the platform uses separate
Kubernetes services. Configuration promotion between editions is not implemented.
Do not market a shared runtime or automatic local-to-enterprise migration.

## Reference projects

The following open-source businesses are explicit references for positioning, visual design,
adoption, and community practice:

- T3 Code — direct developer voice, product-first demonstration, visible social proof, and a
  prominent fork/download path.
- Unsloth — approachable brand, strong documentation and education, broad community surfaces,
  and rapid support for new ecosystem releases.
- Caveman — memorable point of view, quantified proof, transparent technical boundaries, and
  unusually explicit licensing and verification language.
- Ollama — radical simplicity, a near-zero-friction first run, a strong model/integration
  ecosystem, and privacy-led positioning.
- Orca — high-fidelity product theatre, rapid public shipping, changelog discipline, broad
  platform support, testimonials, and community distribution.

Use these as principles rather than visual templates. Preserve the restrained,
spacious design and use product evidence, such as an architecture diagram. Defer
mascot branding until after launch and further public product iterations.

The detailed review and recommendations live in
`docs/research/open-source-reference-projects.md`.

The year-one X, Discord, word-of-mouth, and local-to-enterprise distribution strategy lives in
`docs/strategy/x-discord-growth-strategy.md`.
