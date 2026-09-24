# Executable Specifications

## Definition

An executable specification is a specification that is both human-readable and automatically checkable against the system's behavior.

In ATDD, executable specifications are usually acceptance tests written before implementation. They describe the expected behavior from the user's or customer's point of view and are connected to automation so they can pass or fail repeatedly.

## Core Properties

Executable specifications should be:

- Written in business domain language
- Understandable by business, development, and testing roles
- Based on concrete examples rather than abstract statements alone
- Precise enough to automate
- Checked frequently against the system
- Maintained as part of the living understanding of the product

## Acceptance Tests As Executable Specifications

Acceptance tests are written from the external view of the system. They examine externally visible effects, such as:

- Output produced for a given input
- State changes visible through the system boundary
- Interactions with another system boundary
- Business rules enforced for a user action

They are generally implementation independent, even when their automation requires implementation-specific adapters.

## Specification And Automation Layers

Executable specifications often have two layers:

1. The specification layer, which contains the examples and expected behavior in a readable form.
2. The automation layer, which connects those examples to the system under test.

The specification layer should remain readable by both technical and non-technical participants. The automation layer may contain code, fixtures, adapters, page objects, API clients, or test harnesses.

## Not Just Tests

Executable specifications are tests, but their purpose is broader than defect detection. They are also:

- A shared understanding of expected behavior
- A collaboration artifact
- A precise form of acceptance criteria
- A living documentation source when validated frequently
- A guide for implementation

## Limits

Executable specifications are not the only requirements technique needed. Examples are necessarily incomplete. They should be supported by continued conversation, domain modeling, exploratory testing, and technical tests.

## Sources

- Wikipedia, "Acceptance test-driven development"
- Wikipedia, "Specification by example"
- Wikipedia, "Behavior-driven development"
- Martin Fowler, "Specification By Example"
- Cucumber documentation, "Behaviour-Driven Development"
