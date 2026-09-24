---
name: create-state-class
description: Enforces using reactive state classes instead of multiple let statements in Svelte components. Use when creating or modifying Svelte component state, adding reactive variables, refactoring component logic, or when the user mentions state management in Svelte.
---

# Create State Class

## Purpose

Always prefer a dedicated state class over multiple `let` / `$state` or `let` / `$derived` or any form of Svelte state variable declarations scattered in a Svelte component's `<script>` block. A state class groups related reactive state and exposes explicit methods for mutation, keeping components declarative and behaviour testable outside Svelte.

The following rules also apply to `$derived`.

## Rules

1. **All mutable state lives in a class** — never declare loose `let x = $state(...)` variables at the top of a component. Instead, create a class whose fields use those variable types.
2. **All mutations go through methods** — never assign to a state class field from outside the class. Every write must happen via a named method on the class.
3. **Reads are direct property access** — consumers read values directly on the instance (e.g. `state.count`), no getters required unless computation is involved.
4. **One class per cohesive state group** — if a component manages two unrelated concerns, use two state classes rather than one god-class.
5. **Prefer arrow-function methods** — avoids `this`-binding issues when passing methods as callbacks in templates.
6. **State classes live in `.svelte.ts` modules, never inside `.svelte` files** — define and export the class from a TypeScript module with the `.svelte.ts` extension so the Svelte compiler processes the state variables. The component imports the class and instantiates it. This keeps components declarative and makes state testable in isolation.

## Svelte 5 `$state` in Classes

The `$state` rune works in class fields and in the first assignment inside the constructor. The compiler transforms these into get/set pairs on the prototype backed by private fields.

### Canonical Pattern

State class in a `.svelte.ts` module:

```ts
// counter-state.svelte.ts
export class CounterState {
  count = $state(0);

  increment = () => {
    this.count += 1;
  };

  reset = () => {
    this.count = 0;
  };
}
```

Component imports and instantiates:

```svelte
<script lang="ts">
import { CounterState } from './counter-state.svelte';

const counter = new CounterState();
</script>

<button onclick={counter.increment}>
  {counter.count}
</button>
<button onclick={counter.reset}>
  reset
</button>
```

### Constructor-Initialised Fields

When initial values come from props or external data, assign with `$state` inside the constructor:

```ts
// todo-state.svelte.ts
export class TodoState {
  done = $state(false);

  constructor(text: string) {
    this.text = $state(text);
  }

  reset = () => {
    this.text = '';
    this.done = false;
  };
}
```

### `this`-Binding Caveat

Regular methods lose their `this` context when passed directly as event handlers:

```svelte
<!-- WRONG — `this` will be the <button>, not the class instance -->
<button onclick={todo.reset}>reset</button>

<!-- OK — arrow wrapper preserves context -->
<button onclick={() => todo.reset()}>reset</button>
```

Using arrow-function methods on the class avoids this entirely and is the preferred style.

## Built-in Reactive Classes

For `Set`, `Map`, `Date`, and `URL`, import the reactive versions from `svelte/reactivity` instead of wrapping the built-ins manually.

## Compliance Check

Use `.cursor/hooks/check-state-class.ts` to verify that a change follows this skill's expected code quality rules.

## Anti-Patterns

- **Loose `$state` declarations** — `let count = $state(0)` at component top-level. Wrap in a class.
- **Inline state classes** — defining a state class inside `<script>` instead of in a `.svelte.ts` module. Always extract to a separate file.
- **External mutation** — `state.count += 1` from the template or parent. Add a method instead.
- **Getter-heavy classes** — don't add trivial getters for every field; direct property reads are fine and keep the class lean.
- **Single god-class** — don't lump unrelated state into one class. Split by domain concern.
