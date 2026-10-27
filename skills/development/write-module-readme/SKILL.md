---
name: write-module-readme
description: Use when creating, editing, or reviewing module README.md files or related knowledge Markdown. Applies Open Knowledge Format (OKF) v0.2 with Markdown templates, progressive-disclosure links, and short relevance descriptions.
---

# Write module knowledge in Open Knowledge Format

## Sources and version

- [Google Cloud introduction to OKF](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing) describes v0.1.
- [Canonical OKF specification](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md) specifies v0.2, used by this skill. The article's original repository now points here.

OKF is a portable directory of UTF-8 Markdown files with YAML frontmatter and ordinary Markdown links. Humans and agents can produce and consume the same files without a service, SDK, or prescribed runtime. Frontmatter makes metadata searchable; the body holds curated knowledge; links form a graph beyond the directory hierarchy.

## OKF rules

### Concepts

- Represent one concept per Markdown file. Its identity is its path within the chosen bundle, without `.md`; moving it changes that identity.
- Begin every concept with YAML frontmatter delimited by `---`. A non-empty string `type` is the only always-required field. Types are producer-defined, not a fixed taxonomy.
- `title`, one-sentence `description`, canonical asset URI `resource`, and a list of `tags` are recommended, not mandatory. Omit fields that have no useful value; never invent metadata to fill a template.
- Use structured Markdown for the body. OKF requires no particular body sections. Use `# Schema`, `# Examples`, or `# Computation` only when applicable, not as boilerplate.
- Link concepts using ordinary Markdown links. Relative links are supported; `/path.md` means bundle-root-relative in OKF, not filesystem-root-relative. Choose a bundle root explicitly before using that form.
- Preserve unfamiliar frontmatter fields when editing. Unknown types and missing optional fields do not invalidate a concept.

### Navigation and history

- `index.md` and `log.md` are reserved filenames, not concepts.
- `index.md` lists linked entries under headings, with short descriptions to support progressive disclosure. It has no frontmatter except that a bundle-root index may declare `okf_version: "0.2"`.
- `log.md` is optional history, newest first, under ISO `YYYY-MM-DD` date headings. Do not add one just to repeat Git history.
- `README.md` is not a reserved OKF filename. A README written as an OKF document is a concept and therefore needs `type`; do not mistake a title-only README for a conformant concept or call it the standard's `index.md`.

### Provenance, trust, and freshness

Use these optional v0.2 fields only when useful and supported by evidence:

- `sources`: materials the concept derives from. Each entry requires `resource`; give it a stable `id` when citing a claim with a matching Markdown footnote. Source `author`, `usage_count`, and `last_modified` are optional objective signals, not credibility scores.
- `generated`: records production with `by` and, when known, `at`. Use `<producer>/<version>` for agents, `human:<id>` for people, or `process:<id>` for automation. v0.2 uses `generated.at` instead of v0.1's `timestamp`.
- `verified`: actual confirmation events, each with `by` and `at`; a single mapping is also permitted. Authorship is not verification. Never claim human review that did not happen.
- No `verified` means unverified; non-human verifiers mean machine-confirmed; a `human:` verifier means human-reviewed. These are advisory signals, not access controls.
- `status`: `draft`, `stable`, or `deprecated`; absent means `stable`. `stale_after` optionally records the absolute instant at which content becomes stale.
- Use ISO 8601 datetimes with explicit UTC offsets for timestamp-valued fields. Do not invent dates or refresh them on unrelated edits.

OKF also supports `type: Attested Computation`, with required `runtime` and a sanctioned computation linked or embedded under `# Computation`. Do not introduce this type for ordinary module documentation; consult specification §10 when that contract is actually needed.

## Repository policy: links and short descriptions only

The following restrictions are repository policy, not requirements imposed by OKF:

- A module README primarily helps an agent decide which files to read. Use `type: Software Module`, a concise title and description, and a linked file table of contents.
- Keep descriptions to short relevance cues of at most 160 characters, excluding the leading link and optional separator. Do not reproduce implementation walkthroughs, function or class inventories, signatures, schemas, branching logic, dependency lists, or examples that merely restate the source or tests.
- Limit module README bodies to headings and bullet entries containing a Markdown link followed by one short relevance sentence. Do not include standalone paragraphs, code blocks, tables, or extra context sections, including “Context not available from the code”.
- Link to authoritative ADRs, specifications, or runbooks when relevant; do not copy their explanations, constraints, or rationale into the README.
- Link to child module READMEs rather than flattening their file lists. Exclude caches and generated build artifacts. Never invent links or create a companion knowledge document per source file merely to satisfy OKF.
- Keep the existing `README.md` entrypoint. Do not rename files or add parallel `index.md` files unless explicitly creating an OKF bundle.
- Applying these conventions to selected READMEs does not make the entire repository an OKF bundle. Full bundle conformance requires every non-reserved Markdown file within the declared bundle boundary to have parseable frontmatter and a non-empty `type`.

## Templates and workflow

1. Inspect the target module's files and existing README. Read source as needed to establish accurate relevance cues; do not document inferred behavior as curated knowledge.
2. Start from [the module README template](templates/module-readme.md). Replace every placeholder, include only links that resolve, and adjust entries to the real module. Do not add context sections.
3. When explicitly authoring a bundle navigation file, use [the index template](templates/index.md) instead. It is not a README/concept template. Only a bundle-root index may add version frontmatter.
4. Add optional metadata only when grounded in known facts. Preserve legitimate existing metadata and links; update stale content rather than blindly replacing it with the template.
5. Check YAML validity, `type`, link targets, and concise descriptions. Keep only headings and linked bullet entries in module README bodies. Remove unfilled placeholders, empty headings, extra context sections, and standalone explanations.
6. Update affected links when files move or disappear. OKF consumers tolerate broken links, but repository-authored indexes should not knowingly introduce them.
7. After using this skill to create or edit README files, run all bundled checks below against the target repository. Fix every reported README issue and rerun until all checks pass.

## Required post-edit checks

Resolve the paths below relative to this skill directory, whether using the repository source or an installed copy. Pass the target repository's absolute root path as the required `repository` argument; do not infer it from the skill's installation location or current working directory.

- [requirements.txt](requirements.txt) — Python dependencies shared by agents and CI; use `uv run --with-requirements` with this manifest when running each script.
- [check_module_readmes.py](scripts/check_module_readmes.py) — Run with the repository argument to validate YAML frontmatter in READMEs beneath `src` directories.
- [check_readme_bodies.py](scripts/check_readme_bodies.py) — Run with the repository argument to enforce headings and linked bullets with descriptions of at most 160 characters.
- [check_readme_links.py](scripts/check_readme_links.py) — Run with the repository argument to validate local file and directory links in all repository READMEs, excluding dependencies and generated files.

All three scripts must exit successfully before reporting README work complete. The harness workflow runs these same source scripts directly without installing the skill.

## Scope

Use this skill for module READMEs and explicitly requested related knowledge documents. Do not bulk-convert repository landing pages, ADRs, product documentation, or `SKILL.md` files. The templates define this repository's minimal authoring profile, not additional universal OKF requirements.
