---
name: choose-design-pattern
description: >
  Guides refactoring agents in choosing object-oriented design patterns from
  concrete code smells and architecture problems. Use when refactoring code that
  may benefit from patterns such as Factory Method, Strategy, State, Adapter,
  Facade, Decorator, Observer, Command, Composite, or related OO design patterns.
disable-model-invocation: true
---

# Choose Design Pattern

## Outcome

Concrete code smells lead to a justified pattern candidate or a simpler local refactor.

## Inputs

- Required: Explicit user invocation and concrete code smells in the affected code.
- Optional: Variation axes, repeated edits, coupling evidence, and refactoring constraints.
- Default: Prefer a smaller local refactor when no recurring variation or coupling problem exists.

## Rules

- R1: Apply only when explicitly invoked by the user; read references/decision-tree.md completely before applying.
- R2: Start with the smell, not a preferred pattern; follow root triage and reject patterns when a simpler refactor solves the issue.
- R3: Read the selected pattern's reference file before proposing or implementing its refactor; justify reduced repeated edits or unsafe coupling.

## Workflow

1. Confirm explicit user invocation, read the decision tree, and identify concrete symptoms.
2. Identify the unstable creation, structure, behavior, state, traversal, or notification axis and follow the shortest matching branch.
3. Compare the candidate with a smaller local refactor; read the selected pattern reference before proposing or implementing it.
4. Check the decision against the tree's questions and affected code; verify the proposed change removes the identified repetition or coupling.

## Decisions

| Condition | Action |
|---|---|
| Explicit invocation or concrete smell is missing | Do not apply; ask for explicit direction or the concrete symptom. |
| Variation evidence is absent | Apply the simpler local-refactor default rather than adding a pattern. |
| Candidate fails the decision-tree checks | Revisit triage, compare alternatives, and reject unnecessary structure. |
| Recovery fails | Stop pattern selection and report the unresolved design evidence. |

## Output

Return:
- Selected pattern or simpler refactor and the smell it addresses.
- Decision-tree checks and selected reference read.
- Unresolved trade-offs or evidence gaps.

## Completion criteria

- Explicit user invocation and smell-first triage support the selection or rejection.
- Any selected pattern's reference was read and its advantage over a smaller refactor is established.

## References

- Read `references/decision-tree.md` when applying this skill; the full triage and pattern branches are mandatory. Command paths remain skill-root-relative unless stated otherwise.
- Read `references/README.md` when locating the existing pattern reference index; read the selected reference before proposing or implementing.
