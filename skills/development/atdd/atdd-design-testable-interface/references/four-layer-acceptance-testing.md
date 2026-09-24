# Four Layer Acceptance Testing

## Purpose

This reference describes the four-layer separation of concerns that keeps acceptance tests stable, readable, and independent of how the system is built. It is the structural model behind the "testable interface" in ATDD.

The testable interface is not a production API. It is the test-facing boundary that executable specifications call. That boundary is made of two designed layers: a Domain Specific Language and one or more Protocol Drivers.

## The Four Layers

```txt
Test Cases (Executable Specifications)
        |
        v
Domain Specific Language (DSL)
        |
        v
Protocol Drivers (e.g. API driver, UI driver)
        |
        v
System Under Test (SUT)  +  External System Stubs
```

Each layer has one job and hides the layer below it.

### Layer 1: Test Cases

Test cases are the executable specifications.

- Written in the language of the problem domain.
- Written from the perspective of an external user of the system.
- Atomic: each test starts from a running, functioning system that contains no data.
- Do not share test data between test cases.
- Express only what the system does, never how it does it.

### Layer 2: Domain Specific Language

The DSL is the shared API that test cases call. It is the primary part of the testable interface.

- Shared between test cases and designed to make tests easy to write.
- Allows precision where a test needs it and skims over detail where it does not.
- Achieves that with optional parameters for nearly everything.
- Encodes common start-up tasks, such as registering users or populating accounts.
- Stays focused on domain concepts and stays clean of ideas about how the system works.

### Layer 3: Protocol Drivers

Protocol drivers are translators or adapters. They turn DSL calls into real interactions with the SUT.

- A good pattern mirrors the DSL: `dsl.checkOut` calls into `driver.checkOut`, but with more specific parameters.
- The DSL parses parameters and fills in detail; protocol drivers encode the real interaction with the SUT.
- Create at least one protocol driver per channel of communication the SUT supports (for example one for an API, one for a UI).
- Isolate all test-infrastructure knowledge of the system here, and nowhere else.
- Keep protocol drivers, DSL implementations, harness factories, fakes, and acceptance-only DTOs under test/support directories. They may import and drive public production interfaces, but production source must never import them or expose an acceptance-specific module or factory.

### Layer 4: System Under Test

The SUT is the deployed system under test.

- Deployed using the same tools and techniques as production.
- Production-like: from the SUT's perspective it cannot tell the difference in how it is deployed or configured.
- Reached only through public interfaces. No back-door access for tests.
- External systems it depends on are replaced with stubs at the boundary.

## Design Heuristics

These checks tell you whether a testable interface is at the right level of abstraction.

### Substitutability Test

Imagine throwing the SUT away and replacing it with something completely different that achieves the same goals. The test cases and the DSL should still make sense.

Example: a test for buying a book online should read just as well for a robot buying a book in a physical store.

### Least Technical Person Test

Imagine the least technical person who understands the problem domain reading the test cases. The tests should make sense to that person.

### What Not How

Adopt the language of the problem domain exclusively.

Prefer:

```txt
placeAnOrder
payByCreditCard
```

Avoid:

```txt
fillInThisField
clickThisButton
```

UI mechanics belong in a protocol driver, never in the DSL or the test cases, unless the UI journey itself is the behavior under test.

### Public Interfaces Only

The testable interface exercises the SUT through the same public interfaces a real external user or system would use. Tests never reach into internal state, private methods, or the database directly.

## Growing The Testable Interface

- Start small. Design just enough DSL and protocol driver to make two or three of the most valuable scenarios executable. Expect reuse even at this size.
- Invent the language needed to express a test at the time of writing the test. Do not worry about implementation.
- Then adopt the discipline of a new acceptance test for every acceptance criterion of every story, driving development from those tests.
- Anyone can write a test case, but developers maintain the DSL and protocol drivers in test/support code, so a developer notices first when a test breaks.

## Sources

- Dave Farley, "Acceptance Test Driven Development Guide", continuous-delivery.co.uk
- Dave Farley and Jez Humble, "Continuous Delivery"
