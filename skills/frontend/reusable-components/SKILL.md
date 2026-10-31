---
name: reusable-components
description: >-
  Use when creating, changing, extracting, reviewing, moving, renaming, or deleting
  reusable frontend UI components or shared styling. Weigh REP, CCP, and CRP,
  maintain umbod/frontend/COMPONENT_INDEX.md, and run its dead-link checker.
---

# Reusable components

## Before changing components

- Read `umbod/frontend/COMPONENT_INDEX.md`, linked source, and real consumers before choosing reuse, extension, or creation.
- Read `umbod/project/architecture-records/ADR-007-actor-specific-ui-composition.md`. Shared presentation owns structure and interaction mechanics, not actor eligibility, authorization, inventory fetching, or feature controllers.
- Load `write-module-readme` for index conventions and applicable Svelte/state skills for implementation.

Repository paths are relative to the repository root. Resolve bundled scripts and dependencies relative to this skill directory to absolute paths before running them.

## Choose a reuse boundary

Apply Robert C. Martin's cohesion principles to UI components and supporting modules, not as a requirement to publish each Svelte file separately:

- **REP — Reuse/Release Equivalence:** Keep a coherent reusable contract and its supporting mechanics together. Identify consumers that must adopt and verify changes together; consider shared rollout and compatibility, not invented package releases.
- **CCP — Common Closure:** Group code that changes for the same reasons. Separate shared visual/accessibility mechanics from feature policy, workflow, and data contracts; similarity alone is insufficient.
- **CRP — Common Reuse:** Do not force consumers to take unrelated behavior, actor flags, APIs, or dependencies. Inspect imports, props, snippets, and transitive dependencies.

Balance all three without a fixed score: neglecting CRP burdens consumers with unused functionality and regression checks; neglecting REP makes pieces hard to discover and assemble; neglecting CCP scatters one reason for change across components.

Before extraction or changing index eligibility, state a concise decision in the task response or review:

1. Identify consumers and shared responsibility. Distinguish demonstrated reuse from a credible single-consumer contract; hypothetical reuse alone is insufficient. Import counts and directory names do not establish suitability.
2. Assess REP, CCP, and CRP using source and usage evidence; name the priority and accepted trade-offs.
3. Compare feature-local composition, extending an existing control, extracting a neutral part with feature-owned composition, and splitting an overloaded component. Avoid speculative extension points.
4. Choose **include**, **keep feature-local/exclude**, **split then include the neutral part**, or **defer pending evidence**. State the boundary and consumers requiring verification.

## Curate the index

Include stable controls, fields, feedback, surfaces, layouts, and neutral domain presenters with explicit reuse boundaries. Label interaction helpers and shared CSS foundations separately from visual components.

Exclude feature screens, actor-owned workflows, controller-bound views, internal state helpers, test harnesses, and components requiring unrelated policies or dependencies. Indexing does not authorize moving code into shared directories or bypassing ADR review.

Maintain `umbod/frontend/COMPONENT_INDEX.md` in the same change:

- **Add/extract/split:** assess eligibility, check for equivalents, and index qualifying public pieces under relevant headings, not every implementation file. Reassess the original entry after a split.
- **Modify:** revisit descriptions and eligibility when public behavior, dependencies, ownership, or reasons for change shift; narrow or remove unsuitable entries.
- **Rename/move/delete/merge:** update affected labels and links, including supporting files; remove stale paths and empty headings. Verify any replacement serves the described purpose.
- Preserve concept frontmatter: non-empty `type`, concise `title`, and one-sentence `description`. This is not OKF's reserved `index.md` navigation file.
- Use headings and linked bullets with source paths relative to the index. Descriptions must say what the item is and when to use it in at most 160 characters, excluding link and separator. Keep rationale in the task response or review.
- Mention material reuse limits: submission integration, required context, native/custom dialog behavior, or restricted domain semantics. Verify adoption claims against consumers.
- Preserve the discovery link in `umbod/frontend/src/lib/components/README.md`; update it if the index moves.

## Verify

After adding, deleting, renaming, or moving components, or editing the index, run:

`uv run --with-requirements <absolute-skill-directory>/requirements.txt <absolute-skill-directory>/scripts/check_component_index.py <absolute-repository-root>`

Substitute actual absolute paths. The checker validates local file targets in `umbod/frontend/COMPONENT_INDEX.md` under the explicit repository argument. It does not check external URLs, anchors, catalogue completeness, or cohesion.

Fix reported failures and rerun; do not create placeholders or remove valid entries to silence it. Manually compare component additions/deletions with the index and verify descriptions against source.

- **Module README edits:** run the checks required by `write-module-readme`.
- **UI changes:** run applicable repository frontend tests and browser checks.
- **Checker changes:** run `uv run --with-requirements <absolute-skill-directory>/requirements.txt --with pytest pytest <absolute-repository-root>/umbod/scripts/tests/test_check_component_index.py -q` and check the real repository.
