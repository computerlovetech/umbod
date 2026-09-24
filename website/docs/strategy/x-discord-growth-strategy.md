# Umbod X, Discord, and word-of-mouth strategy

Strategy horizon: September 2026–August 2027

## Executive position

Umbod should not try to build an audience around “enterprise agent governance” as an abstract
category. It should build an audience around a magic moment:

> An agent asks to use a real tool. Umbod knows who is asking, applies a policy, allows or blocks
> the action, and produces a receipt you can understand.

The local-first product makes that moment available to an individual in minutes. The cloud-native,
run-in-a-community deployment makes the same model useful across a company. Distribution should
therefore follow this path:

```text
X discovery
  → local magic moment
  → shareable proof artifact
  → Discord help / participation
  → connector or policy contribution
  → team adoption
  → managed or enterprise deployment
```

X and Discord have different jobs:

- **X creates discovery and narrative velocity.** It makes product progress, ecosystem events,
  useful knowledge, and user stories visible outside the existing community.
- **Discord creates belonging, learning, and contributor density.** It helps someone cross from
  curious visitor to successful user, recognized participant, contributor, and advocate.

The north-star metric should not be followers or Discord members. It should be **weekly activated
Umbod environments**: distinct local or organizational environments that complete at least one
governed tool call in a week. The community and content metrics should be evaluated by how well
they increase that behavior.

## What the reference projects teach us

### T3 Code: personality and social proof are distribution

T3 Code makes its founder-led voice part of the product. Humor, direct language, public posts,
testimonials, downloads, and GitHub are woven together. Users can easily repeat the core idea:
one surface for the coding-agent subscriptions they already have.

What Umbod should borrow:

- A point of view that sounds like a person, not a security-vendor committee.
- Short, visual demonstrations of real workflows.
- Community posts and testimonials linked to the original source.
- “Bring your own agent” as a vendor-neutral distribution advantage.

What Umbod should avoid:

- Founder humor that is copied rather than authentic.
- Repeating social proof without adding new information.
- Letting public enthusiasm imply that every contribution can or will be accepted.

### Unsloth: attach yourself to ecosystem moments

Unsloth repeatedly turns upstream model releases into useful, timely content: quantified
performance, a free notebook, a guide, and something people can immediately run. The project does
not merely announce itself; it helps the community understand and use whatever everyone is already
talking about. One observed Gemma release post combined an accessible hardware threshold, speed and
memory claims, a free notebook, repository, and guide. That structure gives people several reasons
to share it.

What Umbod should borrow:

- Ship compatibility and guidance alongside important MCP, agent, identity, and security events.
- Pair every claim with a runnable recipe or inspectable artifact.
- Treat education, community help, documentation, and code as equally valid contributions.

### Caveman: a contagious idea survives because proof supports it

Caveman has a compact, surprising idea—agents talking like cavemen to save tokens—but sustains
attention through benchmarks, verification ladders, transparent licensing, safety properties, and
an installer that spreads across many agent ecosystems. It gives the community a phrase to repeat
and evidence to defend it with.

What Umbod should borrow:

- A visible proof object: the Umbod governance receipt.
- An explicit ladder from demo to measured production evidence.
- Agent-readable documentation such as `llms.txt` and Markdown endpoints.
- Distribution through the tools and ecosystems users already inhabit.

### Ollama: become a verb through a tiny local action

Ollama's community flywheel begins with a command small enough to remember. New models,
integrations, machines, and personal projects become occasions to use and mention Ollama. Its posts
often attach to an ecosystem launch and point toward one immediate command or model page.

What Umbod should borrow:

- One canonical command and one canonical first success.
- Compatibility with familiar interfaces rather than demanding a new workflow.
- An integration catalog that compounds community value.
- User-created examples as a major content source.

### Orca: public shipping creates continuous narrative inventory

Orca turns a fast release rhythm into a changelog, product clips, testimonials, and repeated
reasons to return. Its website and README offer Discord, X, GitHub, feature requests, multiple
install channels, and multilingual material. Each channel has a useful role.

What Umbod should borrow:

- A dependable public ship log with screenshots or short demonstrations.
- Community stories anchored in specific workflows.
- Clear download, source, feedback, and enterprise paths.

What Umbod should avoid:

- Confusing shipping volume with customer value.
- A feature feed so broad that the core governance story disappears.

## The word-of-mouth design: applying STEPPS

Jonah Berger's framework describes six recurring drivers of word of mouth: Social Currency,
Triggers, Emotion, Public, Practical Value, and Stories. Umbod can intentionally design each one
without resorting to engagement bait.

### Social Currency: make users look competent and responsible

Sharing Umbod should signal: “I know how to let agents move quickly without giving them the keys to
everything.” Useful mechanisms:

- **Governed by Umbod badge** for READMEs, internal portals, and connector pages.
- **Founding Operator** recognition for early community members who complete the local lab and
  help someone else.
- Public connector-author profiles and contributor credits.
- A shareable “agent access architecture” generated from a local configuration with sensitive
  details removed.
- A serious annual “State of Agent Access” report crediting community data and contributors.

The status must be earned through useful behavior, not purchased or handed out for joining.

### Triggers: attach Umbod to recurring moments

Umbod needs environmental reminders that occur when the product is relevant:

- A new MCP server or agent client launches.
- Someone writes “just give the agent an API key.”
- A team debates whether to allow an agent into production systems.
- A security incident involves tokens, permissions, or untraceable automation.
- An engineer creates another bespoke proxy or permission wrapper.
- A company moves from one agent enthusiast to organization-wide rollout.

Build recurring formats around these triggers: “Permission of the week,” “Would you allow this
agent action?”, “MCP launch access review,” and “The API-key replacement pattern.” The goal is for
people to think of Umbod whenever agent access becomes a conversation.

### Emotion: sell relief, confidence, and wonder—not fear

Fear can attract attention in security, but repeated fear creates a defensive, joyless brand.
Umbod's strongest emotional mix is:

- **Wonder:** the agent actually uses a real tool safely.
- **Relief:** access is controlled without blocking experimentation.
- **Confidence:** every action has an intelligible reason and receipt.
- **Belonging:** responsible agent builders are developing the pattern together.

Use incidents to teach, not to shame teams or exaggerate catastrophe.

### Public: turn invisible governance into visible artifacts

Authorization normally happens invisibly, which makes it poor material for imitation. Umbod should
make safe aspects observable:

- A beautiful, redacted decision receipt suitable for screenshots.
- A live local demo that visibly flips from denied to allowed after a policy change.
- Connector and policy badges.
- Public compatibility tests and a status matrix.
- A community gallery of architectures and policy patterns.
- Optional aggregate milestones such as “one million governed tool calls,” only when truthful and
  privacy-preserving.

### Practical Value: give away operational shortcuts

Practical material should form the majority of X output:

- Five-minute local lab.
- Copyable policy recipes.
- MCP connector templates.
- Threat models and access-review checklists.
- “How to govern [new agent or MCP server]” guides published during launches.
- Redacted incident teardowns.
- Decision trees for local, team, and enterprise architectures.

Every useful X thread should have a durable home in docs; valuable knowledge should not disappear
into the timeline or a Discord search box.

### Stories: make the agent action the protagonist

Use a repeatable story structure:

1. An employee asks an agent to accomplish a recognizable task.
2. The agent requests a consequential operation.
3. Umbod identifies the human and evaluates policy.
4. The action is allowed, narrowed, escalated, or denied.
5. A receipt explains what happened.
6. The organization learns or improves a reusable policy.

This structure communicates the product while carrying a human tension: speed versus control.

## X strategy

### Account roles

Use both a brand account and a founder account.

**The Umbod account** is the reliable institutional voice:

- Releases and changelog entries.
- Product clips and governance receipts.
- Integration announcements.
- Documentation, recipes, and community showcases.
- Security and compatibility notices.

**The founder account** supplies interpretation and personality:

- Strong opinions about agent access and organizational adoption.
- Building-in-public decisions and tradeoffs.
- Responses to ecosystem news.
- Stories from user conversations and design-partner work, appropriately anonymized.
- Recognition and amplification of community members.

The founder should not merely repost the brand account. One publishes the fact; the other explains
why it matters.

### Content pillars and mix

Use this as a monthly mix, not a rigid weekly quota:

| Share | Pillar | Examples |
|---:|---|---|
| 35% | Practical operator value | Policy recipes, threat models, local labs, MCP access patterns |
| 25% | Product proof | Short demos, receipts, performance/reliability evidence, releases |
| 20% | Ecosystem participation | New-agent compatibility, MCP launches, open standards, partner projects |
| 15% | Community proof | Connector authors, user builds, answers, deployment stories |
| 5% | Company/enterprise | Design-partner invitations, hiring, commercial capabilities |

This keeps the account useful even to the majority who will never buy enterprise software.

### Sustainable cadence

- Three to five substantive brand posts per week.
- Two short product videos or animated demonstrations per month.
- One durable technical essay, guide, or policy pack per month.
- One community member or project spotlight per week once supply exists.
- Founder participation most weekdays: thoughtful replies, one or two original posts, and selective
  quote-posts where Umbod adds expertise.
- One X Space per month, mirrored by a Discord event, with a practitioner or adjacent open-source
  maintainer.

Avoid daily filler, generic motivational content, automatic thread spam, and engagement bait.

### Repeatable X formats

1. **Would you allow this?** Show an agent action and let people choose allow, deny, narrow, or
   require approval. Follow with the Umbod policy and reasoning.
2. **Receipt of the week.** A visually strong, redacted authorization receipt and the story behind
   it.
3. **Govern this integration.** Release a connector or policy pack alongside an ecosystem launch.
4. **From API key to policy.** Before-and-after architecture in one image.
5. **Local lab Friday.** A task someone can complete in under ten minutes.
6. **What we changed after talking to operators.** A transparent product decision and evidence.
7. **Agent access teardown.** Analyze a public architecture without dunking on its authors.
8. **Community build.** Amplify a connector, recipe, bug fix, article, or deployment.

### Launch sequence

Do not treat launch as one post. Use a three-week narrative arc:

**Seven to ten days before launch**

- Establish the problem with concrete agent-action stories.
- Show pieces of the receipt and local flow without requiring signup.
- Invite a small number of local-lab testers and connector builders.

**Launch day**

- One short product film showing the complete magic moment.
- Repository, one-command quickstart, architecture explanation, Discord, and clear license.
- Separate posts aimed at MCP builders, security engineers, agent enthusiasts, and platform teams.
- Coordinated but non-scripted posts from design partners and early users using their own stories.
- Founder availability for replies, troubleshooting, and live demonstration.

**Following fourteen days**

- Publish fixes and lessons quickly.
- Feature the first successful community deployments.
- Ship one requested connector or policy improvement.
- Hold an open office hour and a technical architecture session.
- Submit genuinely technical launch material to Hacker News and relevant communities; do not ask
  people to upvote it.

## Discord strategy

### The promise

The Discord should be “the workshop for people making agent access safe and useful,” not a support
queue with a chat room attached.

Someone joining should be able to answer three questions within one minute:

1. What is Umbod?
2. What can I do here today?
3. Where do I ask my specific question?

Discord's own guidance warns that too many channels and confusing bot gates cause newcomers to
leave. Start compact and expand only when sustained activity requires it.

### Initial channel architecture

**START HERE**

- `#start-here` — the promise, code of conduct, local quickstart, and where to get help.
- `#announcements` — releases, events, and security notices; low volume.

**BUILD AND LEARN**

- `#general` — discussion and introductions through real work, not forced biography.
- `#help` — a Forum channel with tags such as install, connectors, policies, identity, and cloud.
- `#show-and-tell` — receipts, connectors, policy packs, architectures, and demos.
- `#ideas-and-roadmap` — a Forum channel; accepted work is promoted to public GitHub issues.

**CONTRIBUTE**

- `#contributors` — implementation coordination after someone has found a concrete issue.
- `#connector-lab` — only add when connector discussions are frequent enough to sustain it.

**EVENTS**

- `#office-hours` — event details and follow-up resources.

Do not create empty channels for every agent, provider, language, or feature. Use Forum tags first.

### Onboarding

Enable Community Onboarding and ask one short question: **What are you here to do?**

Options and roles:

- Try Umbod locally.
- Govern agents for a team.
- Build a connector or policy.
- Work on identity/security architecture.
- Contribute to the project.

The selection should personalize recommended channels, not create status hierarchies. Give every
new member three first actions:

1. Run the local lab.
2. Post a successful receipt or ask for help.
3. Choose one connector or policy pattern they want to see.

### Rituals that create belonging

- **Weekly office hour:** installation help, architecture questions, and live product feedback.
- **Friday ship room:** a short demo of what changed, including community contributions.
- **Monthly policy clinic:** members bring a real or hypothetical agent action and design the
  least-privilege policy together.
- **Monthly connector jam:** choose one demanded integration and get it to a working proof.
- **Quarterly community demo day:** users show what they built; clips become X content with consent.

Rituals matter more than channel count. Predictable events create triggers and relationships.

### Contribution ladder

Give members a visible path that does not assume they can write core code:

1. Complete the local lab.
2. Ask or answer a useful question.
3. Share a receipt, policy pattern, or deployment note.
4. Improve a document or reproduce a bug.
5. Build or maintain a connector/policy pack.
6. Host a clinic, review contributions, or mentor a newcomer.
7. Join the trusted maintainer/operator group through demonstrated work.

Recognition should follow contribution. Avoid gamified message-count levels, which reward noise.

### Operating standards

- Publish response-time expectations rather than implying continuous support.
- Ensure every unanswered help thread has an owner during staffed hours.
- Convert resolved, reusable answers into public documentation each week.
- Maintain a clear Code of Conduct and moderation escalation path before launch.
- Keep enterprise customer data and support out of public Discord; use private, contractual support
  channels for sensitive deployments.
- Never encourage users to paste API keys, private policies, internal hostnames, or unredacted
  receipts.
- Recruit moderators from consistently constructive contributors, then train them.

## Local-first to enterprise distribution

The local product is not a miniature enterprise trial and is not expected to carry the primary
revenue burden. It is the distribution and community product: a complete personal utility that
creates adoption, ambassadors, connector and policy authors, public learning, and a credible path
into the organizational product. Enterprise Umbod is the operational and revenue product.

This distinction implies one architectural rule: **share the governance core; vary the operating
envelope**. Policy evaluation, connector contracts, decision receipts, configuration formats, and
the local API should be portable and edition-neutral. Packaging, identity scale, coordination,
availability, administration, compliance, and managed operations are where the editions diverge.

### Cross-platform product shape

Avoid starting with several native desktop implementations. Build one headless, cross-platform
Umbod core with a stable local API and configuration format, then package it through progressively
richer shells:

1. A container image and Docker Compose quickstart for the most reproducible first experience.
2. A single CLI that installs, starts, inspects, upgrades, and exports the local environment.
3. A local web interface served by the core, giving macOS, Windows, and Linux the same product UI.
4. Native desktop wrappers only if later evidence shows that tray behavior, credential storage,
   notifications, or background lifecycle materially improve activation.

The core should expose the same connector SDK, policy format, decision receipt schema, and
configuration bundle in local and enterprise deployments. Platform-specific code should be kept at
the edges: process supervision, secure credential storage, filesystem paths, and OS integration.

This reduces the cross-platform problem from “build three applications” to “ship one portable
service, one web UI, one CLI, and thin platform adapters.” It also allows local users to become
enterprise ambassadors because the concepts and artifacts they learn are the ones their company
would later operate.

### Personal/local job

“Let my agents use useful tools without handing them unrestricted credentials, and show me exactly
what happened.”

The local experience should require no sales contact and ideally no account:

- One-command install.
- Sample tool and policy included.
- Local UI or CLI decision stream.
- Redacted shareable receipt.
- Import/exportable configuration.
- Connector/policy marketplace or catalog.

### Team expansion trigger

The expansion prompt should appear when the user's problem genuinely becomes collaborative:

- More than one human identity needs policies.
- Several environments need synchronized configuration.
- The team needs shared audit retention.
- Policies require approvals or separation of duties.
- Connectors need organizational ownership.
- The company needs SSO, SCIM, support, compliance evidence, or managed operations.

Offer “Create a community deployment” or “Bring this setup to your team,” preserving local
connectors and policies. Do not make users rebuild their successful prototype.

### Enterprise value

Paid value should center on organizational coordination and assurance:

- Managed cloud-native deployment or supported self-hosting.
- High availability, upgrades, backups, and observability.
- Organizational identity, SSO/SCIM, groups, approvals, and delegated administration.
- Policy distribution, audit retention/export, and compliance evidence.
- Private connector lifecycle and enterprise integrations.
- Architecture, implementation, and support.

This is a credible open-source business boundary: individuals discover value locally; organizations
pay to operate the pattern reliably across people, agents, systems, and environments.

## Ethical growth experiments

Run experiments in four-to-six-week windows. Define success before starting and stop tactics that
produce attention without activation.

### 1. The Agent Access Risk Scan

A local-only command inspects an agent setup for broad credentials, missing attribution, and
unbounded operations. It produces a private detailed report and an optional redacted scorecard.

- Viral mechanism: practical value, social currency, public artifact.
- Product bridge: convert one finding into an Umbod policy.
- Guardrail: never upload configuration or shame users; explain limitations clearly.

### 2. Shareable governance receipts

Generate attractive, redacted cards for allowed, denied, narrowed, and approval-required actions.

- Viral mechanism: turns invisible governance into visible proof and story.
- Product bridge: card links to a reproducible local lab or public policy recipe.
- Guardrail: default to removing identities, hostnames, arguments, and sensitive metadata.

### 3. Govern-the-launch

Within forty-eight hours of a meaningful MCP server or agent release, publish a tested Umbod
connector/policy pack and a short demo.

- Viral mechanism: recurring ecosystem trigger and practical value.
- Product bridge: install pack locally; invite maintainers to verify compatibility.
- Guardrail: choose quality over pretending to support every launch.

### 4. Permission puzzles

Publish realistic scenarios where the community chooses allow, deny, narrow, or approve. Reveal a
reference policy and discuss tradeoffs in Discord.

- Viral mechanism: identity, emotion, and participation.
- Product bridge: runnable policy pack.
- Guardrail: there may be several defensible answers; avoid fake certainty.

### 5. Connector bounty weeks

Select a community-requested connector, provide fixtures and validation, and recognize everyone
who moves it forward—not only the final merger.

- Viral mechanism: ownership and ecosystem reach.
- Product bridge: every connector expands utility.
- Guardrail: pay meaningful bounties when asking for production-quality work.

### 6. The State of Agent Access

Publish a transparent annual or semiannual report based on opt-in surveys, public configurations,
and privacy-preserving aggregate product data.

- Viral mechanism: useful benchmark, identity, and PR-worthy story.
- Product bridge: assessment and policy templates.
- Guardrail: publish methodology, sample limitations, and conflicts; do not manufacture a crisis.

### 7. Local-to-team challenge

Invite people to complete three stages: govern one local tool, share a redacted receipt, then bring
the same policy to a second user or environment.

- Viral mechanism: progressive public behavior.
- Product bridge: directly tests expansion mechanics.
- Guardrail: reward learning and useful feedback, not referral spam.

### 8. Integration co-launches

Work with adjacent open-source maintainers on a connector, guide, demo, and joint office hour.

- Viral mechanism: credible borrowed distribution and mutual practical value.
- Product bridge: real compatibility.
- Guardrail: the partner should receive equal value and editorial control over claims about them.

## One-year operating plan

### Phase 1 — Foundation and private rehearsal: September–October 2026

- Finalize the one-command local magic moment and activation instrumentation.
- Create the X accounts' distinct voices and initial content library.
- Set up the compact Discord, onboarding, moderation, privacy guidance, and help workflow.
- Recruit fifteen to thirty founding operators across agent builders, MCP maintainers, identity
  engineers, security practitioners, and platform teams.
- Test receipt sharing, risk scan, five-minute lab, and local-to-team configuration export.
- Produce at least six polished demos and six durable practical guides before public launch.

Exit criteria: at least 70% of invited testers complete one governed call; ten do so without live
founder help; five voluntarily share or explain the experience to someone else.

### Phase 2 — Public launch and learning: November–December 2026

- Run the three-week launch sequence.
- Staff Discord heavily for the first two weeks and turn recurring questions into docs daily.
- Ship fixes quickly and narrate what changed because of community feedback.
- Start weekly office hours, receipt of the week, and local lab Friday.
- Run the first permission puzzle and connector co-launch.

Exit criteria: measure visitor-to-install, install-to-governed-call, governed-call-to-Discord, and
local-to-second-user conversion. Do not declare success based on impressions or stars alone.

### Phase 3 — Build the community product: January–April 2027

- Launch the connector template, validation suite, catalog, and contributor pages.
- Establish connector jams and monthly policy clinics.
- Test the risk scan and govern-the-launch formats.
- Promote reliable helpers into documented contributor and moderator roles.
- Publish case studies covering personal, small-team, and community deployments.
- Test a frictionless path from exported local configuration to a team environment.

Exit criteria: at least 30% of public help questions answered first by peers, repeat contributors
growing month over month, and a measurable share of new activations originating from community
artifacts or integrations.

### Phase 4 — Compound and convert: May–August 2027

- Publish the first State of Agent Access report.
- Run targeted integration co-launches with adjacent open-source projects.
- Develop vertical policy packs for the strongest observed use cases.
- Formalize community maintainership and recognition.
- Introduce enterprise architecture sessions based on demonstrated team expansion, not generic
  lead generation.
- Review channel health and remove rituals or content formats that do not produce activation,
  learning, contribution, or qualified team expansion.

Exit criteria: a repeatable local-to-team conversion path, community-sourced connectors and
education generating meaningful activation, and enterprise pipeline traceable to product use or
trusted community participation.

## Measurement system

### Product and business

- Weekly activated environments.
- Time to first governed call.
- Install-to-activation conversion.
- Four-week retained environments.
- Local configuration exported or used by a second identity/environment.
- Team/community deployments created from local setups.
- Qualified enterprise conversations and pipeline sourced from activated use.

### X

- Qualified link clicks by content pillar.
- Click-to-install and click-to-activation conversion using privacy-respecting campaign links.
- Share/bookmark rate for practical content.
- Earned mentions containing a real use case, receipt, connector, or policy.
- Community artifacts amplified versus posts produced solely by the company.
- Founder reply conversations that lead to testers, contributors, or design partners.

### Discord

- Join-to-first-useful-action conversion within seven days.
- Weekly active members, not total membership.
- Help-question median time to useful response.
- Percentage of questions answered first by community members.
- Resolved answers promoted into durable public docs.
- Members moving up the contribution ladder.
- Show-and-tell posts leading to external shares or product improvements.

### Experiment discipline

For every campaign record:

- Hypothesis.
- Target audience and trigger.
- STEPPS mechanisms being tested.
- Product action expected.
- Primary metric and guardrail metric.
- Result after four to six weeks.
- Decision: stop, revise, standardize, or scale.

## Guardrails

- Never use fear, fake scarcity, inflated counters, or unverifiable security claims.
- Never ask employees or partners to copy coordinated promotional language.
- Never ask communities to manipulate Product Hunt, Hacker News, GitHub, or X engagement.
- Do not expose user identities, prompts, policies, connector arguments, or company architecture in
  shareable artifacts by default.
- Do not let Discord become the only location for important documentation or product decisions.
- Do not measure community health through member count or message volume alone.
- Do not turn open-source contributors into unpaid enterprise support.
- Do not create content faster than the product can fulfill its promise.

## The first six actions

1. Define and instrument the local magic moment: one governed call plus one intelligible receipt.
2. Design the redacted, shareable receipt as both a product feature and the core public artifact.
3. Recruit the founding-operator cohort and privately rehearse Discord onboarding and support.
4. Build the first twelve pieces of launch inventory: six demonstrations and six practical guides.
5. Select three adjacent launch ecosystems—one agent client, one MCP server category, and one
   identity/security community—for tested co-launch material.
6. Establish a weekly growth review using activation, retention, peer help, and team-expansion data.

## Sources

### Reference projects

- T3 Code website and repository: <https://t3.codes/>,
  <https://github.com/pingdotgg/t3code>
- T3 Code contribution policy:
  <https://github.com/pingdotgg/t3code/blob/main/CONTRIBUTING.md>
- Unsloth website, repository, and contribution guidance: <https://unsloth.ai/>,
  <https://github.com/unslothai/unsloth>,
  <https://github.com/unslothai/unsloth/blob/main/CONTRIBUTING.md>
- Caveman website, documentation, licensing, and contribution guidance: <https://caveman.so/>,
  <https://docs.caveman.so/>, <https://docs.caveman.so/docs/licensing>,
  <https://github.com/JuliusBrussee/caveman/blob/main/CONTRIBUTING.md>
- Ollama website, repository, and contribution guidance: <https://ollama.com/>,
  <https://github.com/ollama/ollama>,
  <https://github.com/ollama/ollama/blob/main/CONTRIBUTING.md>
- Orca website, repository, and changelog: <https://www.onorca.dev/>,
  <https://github.com/stablyai/orca>, <https://www.onorca.dev/changelog>

### Word of mouth and Discord

- Jonah Berger, STEPPS and triggers: <https://jonahberger.com/how-to-trigger-word-of-mouth/>
- *Contagious* reading group guide:
  <https://jonahberger.com/wp-content/uploads/2013/01/CONTAGIOUS_RGG_FINAL.pdf>
- Discord Community Onboarding guidance:
  <https://support.discord.com/hc/en-us/articles/11074987197975-Community-Onboarding-FAQ>
- Discord community best practices:
  <https://discord.com/blog/best-practices-for-starting-a-great-community-on-discord>
- Research on how developers promote open-source projects:
  <https://arxiv.org/abs/1908.04219>
- Research on Hacker News promotion and open-source AI projects:
  <https://arxiv.org/abs/2506.12643>
