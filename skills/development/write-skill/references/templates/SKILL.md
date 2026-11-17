---
name: verb-noun
description: >
  [Describe the capability]. Use when [specific task or trigger].
---

# [Skill title]

## Outcome

[Describe the observable result in one sentence.]

## Inputs

- Required: [Information or artifacts needed to proceed.]
- Optional: [Information that improves the result.]
- Default: [Assumption to use when optional information is absent.]

## Rules

- R1: [One mandatory constraint.]
- R2: [One mandatory constraint.]
- R3: [One mandatory constraint.]

## Workflow

1. [Perform one action.]
2. [Perform one action.]
3. [Perform one action.]
4. [Validate the result using a named check.]

## Decisions

| Condition | Action |
|---|---|
| [Required input is missing] | [Ask for the specific missing input.] |
| [An optional input is missing] | [Apply the stated default.] |
| [Validation fails] | [Perform a specific recovery action.] |
| [Recovery fails] | [Stop the affected work and report the blocker.] |

## Output

Return:
- [Primary deliverable and its format.]
- [Verification result.]
- [Any unresolved limitations.]

## Completion criteria

- [Observable acceptance condition.]
- [Observable acceptance condition.]

## References

- Read `references/[file].md` when [specific condition].
- Run `scripts/[script]` to [specific deterministic operation].
