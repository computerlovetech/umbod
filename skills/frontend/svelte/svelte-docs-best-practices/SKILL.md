---
name: svelte-docs-best-practices
description: >-
  Applies official Svelte best practices from the docs (runes, events, snippets,
  each keys, CSS custom properties, context, legacy avoidance), plus this repo’s
  SvelteKit component placement under $lib/components. Use when writing or
  reviewing Svelte 5 / SvelteKit components.
---

# Svelte docs best practices

Authoritative reference: [Best practices • Svelte Docs](https://svelte.dev/docs/svelte/best-practices).

For deep `$effect` review, also load `effect-usage-guard`.

## SvelteKit layout and component placement

Baseline matches [Project structure • SvelteKit](https://svelte.dev/docs/kit/project-structure): `src/routes` for routes, layouts, and page `+*.svelte` / server modules; `src/lib` for shared application code (import via `$lib`); `static` for static assets; config at the project root.

**This repository:** reusable `.svelte` components belong under **`src/lib/components/`**, not next to routes. Organize them in **subfolders by domain** (who uses them or what feature they belong to), not as a flat dump. Examples:

- Admin-only UI for a feature: `src/lib/components/admin/booking-links/CopyBookingLinkModal.svelte`
- Cross-cutting marketing UI: `src/lib/components/ContactForm.svelte` or a small subtree if the surface grows

Route files (`+page.svelte`, `+layout.svelte`) should stay **thin**: compose imported components and wire data, actions, and URLs. Colocated non-component modules next to a route (for example `+page.server.ts`, `*.svelte.ts` state classes) are fine when they are route-specific; if multiple routes or `lib` need the same module, move it under `$lib` on a sensible path.

**Verify:** new or moved UI is not introduced as `src/routes/**/SomeWidget.svelte` unless explicitly one-off and not reused—default is `$lib/components/<domain>/...`.

## $state

- Use `$state` only for values that must drive template, `$derived`, or `$effect` updates; otherwise use plain `let`.
- For large objects or arrays that are **reassigned** but not deeply mutated (typical API payloads), prefer `$state.raw(...)`.
- **Verify:** grep the file for `$state(`; each binding should either appear in markup/`$derived`/`$effect` or be justified as intentionally non-display reactive work.

## $derived

- Prefer `$derived` for values computed from other reactive state; avoid `$effect` that only mirrors state.
- Use `$derived(expr)` for expressions; use `$derived.by(() => ...)` when a function is required.
- **Verify:** no `$effect` whose body only assigns a local from other state without imperative I/O; those should be `$derived` / `$derived.by`.

## $effect

- Treat `$effect` as an escape hatch; avoid updating reactive state inside effects.
- Prefer `{@attach ...}` for imperative DOM/library wiring when it fits; prefer event handlers for user-driven work; prefer `$inspect` for debug observation; prefer `createSubscriber` for external observation patterns described in the docs.
- Do not wrap the effect body in `if (browser) { ... }` (effects do not run on the server).
- **Verify:** effects do not assign to `$state` / props mirrors unless there is explicit external integration; no `browser` guard around the whole effect callback.

## $props

- Assume props change over time; any value derived from props should be `$derived` (or `$derived.by`), not a one-time `let` initializer.
- **Verify:** search for `let { ... } = $props()` and ensure downstream values that reference props are declared with `$derived`, not `let x = f(prop)`.

## $inspect.trace

- Use `$inspect.trace(label)` at the top of an `$effect` or `$derived.by` (or helpers they call) when debugging unexpected updates or dependency churn.
- **Verify:** when fixing reactivity bugs, confirm trace was used or explain why it was not needed.

## Events

- Use attribute event listeners (`onclick={...}`, `{onclick}`, or spread props containing `on*` keys), not legacy `on:click`.
- For `window` / `document` listeners, use `<svelte:window>` / `<svelte:document>` instead of `onMount` / `$effect` solely for that purpose.
- **Verify:** no `on:` event directives in new or touched code; window/document listeners are not mounted exclusively via lifecycle hooks for global events.

## Snippets

- Define reusable markup with `{#snippet ...}` and invoke with `{@render ...}`; prefer over legacy slots where the project is on runes mode.
- Top-level snippets can be referenced from `<script>`; state-free snippets can live in `<script module>` and be exported when needed.
- **Verify:** new composition APIs use `{#snippet}` / `{@render}` rather than `<slot>` / `$$slots` in edited areas.

## Each blocks

- Always key `{#each}` with a stable unique id from the item; never use the index as the key when items can reorder or insert/delete.
- Avoid destructuring the each item if you need to mutate it (for example with `bind:` on nested fields).
- **Verify:** each block has `(item.id)` (or equivalent stable key); grep does not show `{#each arr as item, i (i)}` for mutable lists.

## JavaScript values in CSS

- Thread JS values into `<style>` via CSS custom properties using the `style:` directive (for example `style:--columns={columns}`), then reference `var(--columns)` in CSS.
- **Verify:** dynamic layout values used in CSS are not string-concatenated into `class` or raw `style` when a custom property would keep concerns separated.

## Styling child components

- Prefer passing custom properties (`<Child --token="value" />` with `var(--token)` in the child) over reaching into child markup.
- If the child is from a library and tokens are impossible, scope `:global` overrides narrowly under a parent wrapper selector.
- **Verify:** new parent→child theming uses `--*` props before adding broad `:global` rules.

## Context

- Prefer context over shared modules for state that should be scoped to a subtree (especially under SSR, avoids cross-request leakage).
- Prefer `createContext` over raw `setContext` / `getContext` when the API is available in the project’s Svelte version.
- **Verify:** new cross-component state that must not be global uses context, not a new singleton module, unless explicitly environment-safe.

## Async Svelte (experimental)

- `await` in components and `<hydratable>` require Svelte ≥ 5.36 and `experimental.async` in `svelte.config.js`; treat as opt-in, not default guidance.
- **Verify:** if using async features, `svelte.config.js` enables the flag and the team accepts experimental status.

## Avoid legacy features (new and touched code)

Prefer, when editing or adding code:

| Instead of | Use |
|--------------|-----|
| implicit reactive `let` / `$:` | `$state`, `$derived`, `$effect` (last resort) |
| `export let`, `$$props`, `$$restProps` | `$props` |
| `on:click` | `onclick` |
| `<slot>`, `$$slots`, `<svelte:fragment>` | `{#snippet}` / `{@render}` |
| `<svelte:component this={Ctor}>` | `<Ctor />` (use the constructor directly; see [v5 migration](https://svelte.dev/docs/svelte/v5-migration-guide)) |
| `<svelte:self>` | `import Self from './ThisComponent.svelte'` then `<Self />` |
| stores for shared reactivity | classes with `$state` fields where appropriate |
| `use:action` when attach fits | `{@attach ...}` |
| `class:` directives | `class` with clsx-style arrays/objects |

- **Verify:** grep touched files for legacy patterns above; each hit is either outside the edit scope (document why) or migrated.

## PR self-check (copy)

- [ ] New Svelte components live under `$lib/components/` with a domain-appropriate subfolder
- [ ] Reactive locals justified (`$state` / `$state.raw`)
- [ ] No effect-only derivations
- [ ] Prop-derived values use `$derived`
- [ ] Keyed `{#each}` with stable ids
- [ ] Events use `on*` attributes; globals use `<svelte:window>` / `<svelte:document>`
- [ ] JS→CSS via `style:` custom properties
- [ ] Child styling prefers `--*` props over `:global`
- [ ] No new singleton module state that should be context-scoped under SSR
