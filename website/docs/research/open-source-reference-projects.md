# Open-source reference projects

Research date: 2026-09-03

## Executive synthesis

The six projects win through different aesthetics, but share the same operating system:

1. They explain one concrete job in the first screen.
2. They let a developer install, download, or inspect source immediately.
3. They show the real product rather than illustrating an abstract category.
4. They turn public momentum into trust through stars, releases, testimonials, changelogs, or
   new-model support.
5. They create several community doors: GitHub for building, Discord/Reddit for support, social
   channels for distribution, and docs or a changelog for ongoing education.

Umbod already has a clean visual identity and a legible enterprise problem. Its biggest gap is
evidence: the current page describes an open-source product that visitors cannot yet inspect,
install, see in operation, or discuss in a live community.

## Comparative snapshot

| Project | Core promise | Visual approach | Adoption loop | Community loop | Main risk |
|---|---|---|---|---|---|
| T3 Code | One control plane for coding agents | Dark, irreverent, product-heavy | Download or fork immediately | Creator reach, Discord, GitHub, testimonials | Contribution policy is intentionally restrictive; star count on site can lag GitHub |
| Unsloth | Run and train models locally | Friendly, bright, soft green, mascot-led | Platform-aware download plus docs | GitHub, Discord, Reddit, tutorials, model-release content | Homepage breadth can obscure the original fine-tuning wedge |
| Caveman | Cut agent token cost and prove savings | Dark, technical, quantified, distinctive mono details | One install action, quantified outcome | GitHub virality, docs, reproducible evals, starter issues | “Open” is nuanced because core runtime is BSL/source-available, not wholly open source |
| Ollama | Run open models simply and privately | Minimal black-and-white, large whitespace | Two-minute download and stable CLI/API | Model ecosystem, integrations, Discord, blog | Simplicity hides operational detail; proof and pricing claims require careful upkeep |
| Orca | Run many coding agents in one ADE | Dark, polished, high-fidelity product theatre | Native download, package managers, source | Daily releases, changelog, Discord, X, multilingual README | Very long page and extremely broad feature set can dilute the primary story |
| Hermes Agent | A personal agent that lives on your machines and channels | Dark, product-led, platform artwork per OS | `curl \| bash` one-liner plus native installers | GitHub, Discord, X, Nous Portal | Broad capability list and a hosted portal blur the local-first story |

Repository scale observed through the GitHub API on the research date: T3 Code ~21.5k stars,
Unsloth ~75.5k, Caveman ~102.8k, Ollama ~180k, and Orca ~60.4k. Treat these as a dated snapshot,
not permanent marketing copy.

## T3 Code

### What it is and why it works

T3 Code is an MIT-licensed desktop/mobile control plane for multiple coding-agent harnesses. Its
best strategic choice is “bring your own subscription”: it sits above tools developers already
pay for rather than asking them to replace models or buy tokens again. The page makes the open
source consequence concrete with “fork it,” “change the UI,” “add an agent,” and “ship your own
build.”

The adoption path is unusually direct: a platform download is the primary action, GitHub is the
secondary action, and mobile options follow immediately. Product sections demonstrate specific
workflows—agent threads, diffs, commit/push, and PR creation—instead of listing generic benefits.

### Visual review

The site uses an almost-black grid, a large centered white headline, floating model/provider
icons, and a product screenshot that enters the first viewport from below. Rounded controls and
subtle depth make it feel like a premium developer tool without becoming visually noisy. Its
irreverent copy (“Steal our code (legally),” “Tolerated by…”) creates a recognizable founder-led
voice.

### Community and operating practice

- GitHub, Discord, desktop releases, mobile stores, package registries, and public testimonials
  provide distinct adoption and advocacy paths.
- Repository docs include architecture, glossary, provider guides, CI gates, release runbooks,
  and observability material.
- Releases are extremely frequent, including nightly builds, which turns shipping cadence into
  a public narrative.
- Contribution expectations are honest: small bug, reliability, and performance fixes are most
  likely to be accepted; large unsolicited features are not.

### What does not work as well

- The contribution stance protects direction but leaves enthusiastic contributors with few
  meaningful ways to graduate into trusted maintainers.
- The humor is memorable but not transferable to every audience; copied without an authentic
  founder voice it would feel artificial.
- The homepage star count was behind the live GitHub count during review, showing the maintenance
  cost of hard-coded social proof.
- Heavy testimonial repetition increases page length without always adding new evidence.

## Unsloth

### What it is and why it works

Unsloth is an open-source local AI and model-training ecosystem spanning fine-tuning, inference,
quantization, a desktop UI, notebooks, and integrations. It reduces adoption anxiety with three
plain claims: open source, free, and local. Platform-aware downloads and a visible “Learn more”
path serve both impatient and cautious users.

Its durable moat is educational and ecosystem speed. The site continuously publishes model
guides and day-zero support for important releases, creating useful content at exactly the moment
developers search for it.

### Visual review

Unsloth is the warmest of the set: white space, pale mint gradients, a small sloth mascot, pill
navigation, rounded panels, and clean desktop screenshots. The interface feels safe and
approachable despite technically dense subject matter. The hero gives the product screenshot
roughly half the initial narrative weight.

### Community and operating practice

- Community entry points include GitHub Discussions, Discord, Reddit, X, LinkedIn, a newsletter,
  docs, blog posts, and notebooks.
- Contribution guidance explicitly values code, ideas, helping others, documentation, and
  spreading the word—not only pull requests.
- A Code of Conduct and focused PR expectations create a more welcoming contribution surface.
- Partnerships and compatibility work with model teams allow Unsloth to participate in upstream
  release narratives.

### What does not work as well

- The product surface is now so broad that a new visitor can struggle to identify the single
  canonical first use case.
- The homepage becomes a long sequence of feature blocks; several compete for equal importance.
- Multiple licenses across components require care so “open source” remains precise everywhere.
- Hardware/model-specific performance claims age quickly and need dates, test conditions, and
  reproducible methodology.

## Caveman

### What it is and why it works

Caveman is a token-efficiency stack for agents. It began with a humorous, instantly explainable
skill and expanded into compression, memory, proxy, SDK, and hosted platform layers. The sharp
promise—cut AI costs—and the deliberately primitive brand make it easy to retell.

Its strongest practice is proof architecture. The site distinguishes inferred, replayed, and
verified savings, starts verified savings at zero, describes fail-closed behavior, publishes
benchmarks/evals, and exposes provider pricing assumptions. This addresses the largest credibility
problem in optimization products: impressive numbers that cannot survive scrutiny.

### Visual review

Caveman uses a near-black palette, oversized high-contrast typography, green dot matrices, mono
labels, ledger-like receipts, and numbered technical sections. The hero converts “65%” into a
visual measurement rather than decorative artwork. It feels like a serious infrastructure system
wearing a playful name.

### Community and operating practice

- A one-command multi-agent installer distributes the project through many existing ecosystems.
- Documentation is friendly to both people and agents, including `llms.txt`, `llms-full.txt`, and
  Markdown variants generated from the same source.
- Contribution docs identify sources of truth, generated mirrors, tests, benchmarks, starter
  issues, and concrete extension points.
- Licensing, telemetry, safety behavior, benchmarks, and claim boundaries are unusually explicit.

### What does not work as well

- The homepage can imply a more uniformly open-source system than the license map supports: core
  engine-linked runtime is BSL 1.1/source-available, while adoption surfaces are MIT and hosted
  cloud is commercial.
- The claimed percentage is memorable but can dominate understanding of the actual stack.
- Dense technical storytelling and long pages reward experts but can overwhelm a curious first-time
  user.
- The brand joke creates reach, but enterprise trust ultimately depends on the proof and governance
  material doing more work than the joke.

## Ollama

### What it is and why it works

Ollama is the default local runtime and distribution layer for many open models. Its foundational
success is a tiny mental model: install Ollama, run a model by name, and talk to a stable local API.
The broader ecosystem—model library, integrations, community applications, and OpenAI-compatible
interfaces—turns that simple primitive into a platform.

The current homepage expands the promise into cloud usage while retaining the privacy and local
story. It uses concrete rails: speed, model capability/cost, existing agent integrations, data
handling, and predictable pricing.

### Visual review

Ollama is radically minimal: black type on white, the small llama mark, enormous whitespace, one
black download button, and a large real-product visual. Muted customer logos provide credibility
without competing with the hero. The restraint makes the product feel inevitable rather than
sales-led.

### Community and operating practice

- A stable CLI/API and model packaging format make third-party integrations the primary community
  growth loop.
- GitHub, Discord, docs, a blog, integrations, and the model library separate support, education,
  and discovery.
- Contribution guidance prioritizes bugs, performance, security, compatibility, focused changes,
  tests, and low maintenance burden.
- Local privacy and open weights attract users whose requirements are poorly served by closed
  hosted products.

### What does not work as well

- The homepage's minimalism leaves architecture, security, and deployment questions to the docs.
- Large trust-logo walls can feel unsubstantiated unless the meaning of “trusted by” is clear.
- Benchmark and comparative-cost claims need continuous refreshing and methodology links.
- As cloud features grow, the brand must keep the boundary between local behavior and hosted
  behavior unmistakable.

## Orca

### What it is and why it works

Orca positions itself as an agent development environment rather than another IDE wrapper. It
combines parallel worktrees, multiple CLI agents, terminal, browser, diff review, remote execution,
mobile control, and integrations. “Bring your own agent/subscription” removes provider lock-in and
maps closely to Umbod's vendor-neutral thesis.

Its strongest commercial pattern is giving away a complete MIT-licensed product while reserving an
obvious enterprise conversation for organizational needs. Native downloads and package-manager
commands shorten the self-service path.

### Visual review

Orca uses a black stage, large centered headline, compact credibility strip, white primary CTA,
and an exceptionally detailed product mockup. Tabs change the hero demonstration, so one visual
explains several high-value workflows. Product screenshots, mobile screens, diffs, terminals, and
testimonials continue through the page. The design sells operational reality, not an abstract AI
metaphor.

### Community and operating practice

- GitHub, Discord, X, feature requests, multilingual READMEs, docs, and a public changelog support
  distinct community roles and regions.
- Public daily shipping makes momentum visible and gives advocates frequent material to share.
- Cross-platform desktop support, mobile companions, package managers, and SSH broaden the set of
  users who can participate.
- Testimonials link to their original public posts, making social proof inspectable.

### What does not work as well

- The landing page is extremely long and feature-dense; differentiation can blur after the first
  few sections.
- “100x” is attention-grabbing but not a credible measurable promise for every user.
- Rapid feature expansion creates documentation, support, and quality-pressure risks.
- A very large open issue surface can make contributor wayfinding and maintainer responsiveness
  harder unless actively curated.

## Hermes Agent

### What it is and why it works

Hermes Agent is Nous Research's MIT-licensed personal agent — "the agent that grows with you."
It runs on the user's own machines and reaches them through the channels they already use
(Telegram, Discord, Slack, WhatsApp, Signal, email, CLI), with persistent memory, natural-language
scheduling, delegated subagents, browsing, and sandboxed execution across several backends.

Its relevance to Umbod is the install path. The primary action is a single copyable line:

```
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

The script is served from the marketing domain itself rather than from a release host, which keeps
the command short, memorable, and identical everywhere it is quoted. Platform-specific artwork and
native installers sit alongside it for people who do not pipe to a shell. This is the same shape
Umbod is adopting: one line on the site, a package-manager route beside it.

### Visual review

Dark, product-led, with per-OS artwork for macOS, Windows, and Linux and a capability grid that
names six concrete jobs rather than an abstract category. The install command is treated as hero
content, not a footnote in docs.

### Community and operating practice

- GitHub (<https://github.com/NousResearch/hermes-agent>), Discord, and X provide separate building,
  support, and distribution doors.
- A research-lab identity carries credibility that a product page alone would have to earn.
- The Nous Portal offers model access tiers next to the free local agent.

### What does not work as well

- Hosting `install.sh` on the marketing domain means site availability and installer availability
  become the same dependency, and the script must be versioned as carefully as a release artifact.
- A `curl | bash` primary CTA still asks for trust that a signed package or checksum would earn more
  cheaply; the page does not show a verification path.
- The breadth of channels and sandbox backends is impressive but makes the first-run promise harder
  to state in one sentence.
- The hosted portal and credit tiers sit close enough to the local agent that the local-first claim
  needs careful framing.

## Recommendations for Umbod

### 1. Replace “coming soon” with one real open-source action

Before further visual work, publish a repository or a clearly scoped public starter component.
The primary CTA should lead to a real quickstart such as `docker compose up`, a CLI install, or a
hosted demo. The current CTA eventually reaches placeholder community links, breaking the promise
of fast self-service first value.

### 2. Put the actual product in the first viewport

Keep the bear, but make it an accent or guide beside a real Umbod interface. Show one governed
agent request moving through identity, policy, connector, decision, and audit receipt. T3, Unsloth,
Ollama, and Orca all make the product visible immediately; Umbod currently asks the mascot to carry
too much explanatory weight.

### 3. Narrow the hero to a developer-recognizable first job

“Scale agents. Stay in control.” is polished but broad. Pair it with a concrete wedge, for example:
“Give Claude, Codex, and every MCP client governed access to internal tools—from one self-hosted
control plane.” Then make the CTA describe the result: “Run Umbod locally” rather than “Get
started.”

### 4. Build a five-minute golden path

Create one copyable quickstart that installs Umbod, connects a sample MCP/API, applies one policy,
and shows an audit event. Include expected output and a cleanup command. Time it continuously in CI.
The target is a first successful governed tool call in under five minutes.

### 5. Turn governance claims into inspectable proof

Borrow Caveman's proof discipline. Show a real policy decision receipt with subject, agent/client,
connector, operation, decision, reason, timestamp, and trace ID. Publish a threat model, security
policy, telemetry statement, data-flow diagram, and explicit fail-open/fail-closed behavior.

### 6. Establish separate community doors

Launch GitHub Discussions or Discord only when someone can actively tend it. Use GitHub Issues for
bugs and proposals, Discussions/Discord for help, a changelog for shipping, and a lightweight blog
or examples gallery for education. Give non-code contributors named roles: test an integration,
write a connector guide, share a policy pattern, answer a question, or document a deployment.

### 7. Make integrations the community growth engine

Publish a small connector SDK/template, validation suite, compatibility badge, and public catalog.
Feature community-built connectors on the website. This gives Umbod the equivalent of Ollama's
model ecosystem and Unsloth's model-release content: every new integration becomes useful software,
documentation, and a distribution event.

### 8. Publish contribution and product-boundary rules early

Add `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, a governance/maintainer model, issue
templates, and a public roadmap. Be explicit about which changes are welcome, which require an
issue first, what is stable, and what belongs to enterprise. Clear boundaries are more respectful
than an apparently open contribution funnel that is not maintained.

### 9. Create a visible shipping rhythm

Add a concise changelog and release notes with screenshots or short clips. Prefer a dependable
weekly/biweekly cadence over performative “daily shipping.” Automatically surface the latest
release, compatibility changes, and meaningful contributor credits on the site.

### 10. Preserve Umbod's restraint while adding evidence

Do not copy the references' dark palettes or long pages wholesale. Keep Umbod's white space,
black typography, green accent, and bear identity. Add one strong product demonstration, one
architecture flow, one real governance receipt, a small proof strip, and direct community/source
links. The next design should feel more real, not merely more full.

## Suggested implementation order

1. Public repository, license, security policy, and contribution boundaries.
2. Five-minute quickstart and one sample connector.
3. Real product capture and governance receipt in the homepage hero.
4. Live GitHub/community links and a supported help channel.
5. Connector catalog and contributor recognition.
6. Changelog, public roadmap, case studies, and enterprise proof.

## Primary sources

- T3 Code: <https://t3.codes/>, <https://github.com/pingdotgg/t3code>,
  <https://github.com/pingdotgg/t3code/blob/main/CONTRIBUTING.md>
- Unsloth: <https://unsloth.ai/>, <https://unsloth.ai/docs>,
  <https://github.com/unslothai/unsloth>,
  <https://github.com/unslothai/unsloth/blob/main/CONTRIBUTING.md>
- Caveman: <https://caveman.so/>, <https://docs.caveman.so/>,
  <https://docs.caveman.so/docs/licensing>, <https://github.com/JuliusBrussee/caveman>,
  <https://github.com/JuliusBrussee/caveman/blob/main/CONTRIBUTING.md>
- Ollama: <https://ollama.com/>, <https://docs.ollama.com/>,
  <https://github.com/ollama/ollama>,
  <https://github.com/ollama/ollama/blob/main/CONTRIBUTING.md>
- Hermes Agent: <https://hermes-agent.nousresearch.com/>,
  <https://github.com/NousResearch/hermes-agent>
- Orca: <https://www.onorca.dev/>, <https://www.onorca.dev/changelog>,
  <https://github.com/stablyai/orca>
