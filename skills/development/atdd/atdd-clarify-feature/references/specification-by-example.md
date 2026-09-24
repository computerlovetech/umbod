# Specification By Example

## Definition

Specification by Example is a collaborative approach to defining requirements and business-oriented functional tests by capturing realistic examples instead of relying only on abstract requirement statements.

It overlaps with ATDD, executable requirements, agile acceptance testing, example-driven development, and BDD.

## Why Examples Matter

Abstract or novel concepts can be hard to understand without examples. Concrete examples reduce ambiguity and shorten feedback loops.

Examples help teams:

- Build accurate shared understanding
- Find missing requirements earlier
- Reduce rework
- Improve product quality
- Align business, testing, analysis, and development work

## Single Source Of Truth

A key practice is creating one shared source of truth about the desired behavior.

Without shared examples, analysts may maintain requirement documents, developers may maintain technical notes, and testers may maintain separate test cases. These can diverge.

With Specification by Example, the same examples are used as:

- Requirements clarification
- Acceptance criteria
- Business-oriented functional tests
- Future documentation of existing behavior

## Key Practices

Successful teams commonly apply these patterns:

- Derive scope from goals
- Specify collaboratively
- Illustrate requirements using examples
- Refine specifications
- Automate tests based on examples
- Validate the software frequently using the tests
- Evolve a documentation system from specifications with examples

## Relation To Living Documentation

When examples are automated and run frequently, they become a reliable source of information about business functionality. This is living documentation.

Living documentation should change when the intended behavior changes. If implementation changes but intended behavior does not, living documentation should remain stable.

## Applicability

Specification by Example is most useful when the challenge is understanding and communicating business/domain behavior.

It is less useful for purely technical tasks where domain ambiguity is not the main risk.

## Agent Guidance

When using ATDD skills:

- Prefer concrete examples over abstract criteria alone.
- Use examples to uncover questions.
- Treat the scenario artifact as the shared source of truth for behavior.
- Keep examples readable by non-technical stakeholders.
- Do not replace technical tests with acceptance examples; use both where useful.

## Sources

- Wikipedia, "Specification by example"
- Martin Fowler, "Specification By Example"
- Wikipedia, "Acceptance test-driven development"
