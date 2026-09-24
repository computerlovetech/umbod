# Umbod Website Context

## Purpose

The Umbod website is one landing page for platform teams evaluating self-hosted agent
infrastructure on Kubernetes. Its immediate purpose is to help engineers understand
Umbod, try it locally, and give useful feedback. Local installation is the primary
call to action; feedback and collaboration with Computerlove are secondary.

Explain connectors, group permissions, and independence from agent vendors in concrete
terms. Keep documentation accessible and distinguish current beta capabilities from
future plans. Avoid sales language, pricing tiers, and claims of production readiness.
The local evaluation path does not need a separate landing page for individuals.

## Product strategy

Umbod has two deliberately connected products:

- **Local Umbod is the distribution and community product.** It should be genuinely useful to an
  individual, easy to run across developer platforms, and capable of creating users, ambassadors,
  connector authors, policy authors, and community knowledge. It is not merely a limited enterprise
  trial.
- **Enterprise Umbod is the operational and revenue product.** It takes the same connector, policy,
  identity, and audit model into shared cloud-native environments with organizational identity,
  administration, reliability, compliance, support, and managed operations.

The local and enterprise editions must share a portable core rather than becoming separate product
implementations. A successful local configuration should promote into a team or enterprise
environment without being rebuilt.

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
