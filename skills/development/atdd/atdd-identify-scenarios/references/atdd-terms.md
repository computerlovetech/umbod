# ATDD Terms

## Acceptance Test-Driven Development

Acceptance Test-Driven Development is a development methodology based on communication between business customers, developers, and testers.

ATDD emphasizes writing acceptance tests before coding starts. It is closely related to TDD, but differs by putting stronger emphasis on collaboration between business, development, and testing roles.

## Acceptance Test

An acceptance test verifies expected behavior from the user's point of view. It checks externally visible effects of the system.

An acceptance test may verify:

- A result produced by the system
- A business state transition
- An error or rejection
- An interaction through a public system boundary
- A business rule

## Acceptance Criterion

An acceptance criterion describes what would be checked by a test.

Example:

- Requirement: As a user, I want to check out a book from the library.
- Criterion: Verify the book is marked as checked out.

The acceptance test adds enough detail and data that the criterion can be checked with the same effect each time.

## Scenario

A scenario is a concrete example of expected behavior. In ATDD and BDD it is commonly written as:

```txt
Given <starting context>
When <action or event>
Then <observable outcome>
```

Scenarios can include `And` steps to add more context, actions, or expected outcomes.

## Concrete Example

A concrete example includes specific data, not only general statements.

General scenario:

```txt
Given a book that has not been checked out
And a registered user
When the user checks out the book
Then the book is marked as checked out
```

Concrete example:

```txt
Given book "Great book" is not checked out
And user "Sam" is registered
When "Sam" checks out "Great book"
Then "Great book" is checked out by "Sam"
```

Concrete data helps expose missing or ambiguous requirements.

## Ubiquitous Language

A ubiquitous language is a shared domain language used by business and technical participants. In ATDD, acceptance tests should use this language so customers, developers, and testers can discuss the same behavior without translation.

## Living Documentation

Living documentation is documentation that stays reliable because it is validated frequently by automated checks. Specifications with examples can become living documentation when the examples are automated and maintained as the system evolves.

## Specification By Example

Specification by Example is a collaborative approach to defining requirements and business-oriented functional tests using realistic examples instead of abstract statements alone.

It aims to create a single source of truth that can serve as both specification and business-oriented acceptance test.

## Behavior-Driven Development

Behavior-Driven Development is an agile software development method centered on collaboration and shared understanding. It commonly uses structured natural language to describe behavior and expected outcomes.

BDD overlaps with ATDD and Specification by Example. In this skillset, use BDD-style Given/When/Then as a practical scenario format without treating BDD tooling as required.

## Three Amigos

The three amigos are business, development, and testing perspectives collaborating on requirements.

- Business defines the problem and value.
- Development evaluates how the system can support the behavior.
- Testing questions assumptions and explores what-if scenarios.

An agent applying ATDD should simulate these perspectives when stakeholders are not all present and should ask the user when a decision requires real product input.

## Sources

- Wikipedia, "Acceptance test-driven development"
- Wikipedia, "Specification by example"
- Wikipedia, "Behavior-driven development"
