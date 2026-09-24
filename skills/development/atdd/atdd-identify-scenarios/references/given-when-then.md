# Given When Then

## Purpose

Given/When/Then is a structured way to describe a concrete behavior example.

It separates:

- The starting context
- The action or event
- The observable result

This structure helps turn requirements into acceptance tests that can be discussed, automated, and repeatedly checked.

## Structure

```txt
Given <specified state of the system>
When <action or event occurs>
Then <state changed or output produced>
```

`And` may be used in any section to add more context, actions, or expectations.

## Given

`Given` describes the observable starting context.

Good Given steps describe domain state:

```txt
Given book "Great book" is available
And user "Sam" is registered
```

Avoid implementation setup:

```txt
Given row 123 exists in the books table
And the BookRepository mock returns true
```

## When

`When` describes the action or event that triggers behavior.

Good When steps describe user or system actions:

```txt
When "Sam" checks out "Great book"
```

Avoid UI or implementation mechanics unless the UI itself is the behavior under test:

```txt
When the user clicks the third blue button
When checkoutBook() is called with id 123
```

## Then

`Then` describes the observable outcome.

Good Then steps describe visible results or business state:

```txt
Then "Great book" is checked out by "Sam"
```

Avoid implementation assertions:

```txt
Then BookService.save was called once
Then the cache contains key book:123
```

## Concrete Data

A complete acceptance test should include concrete example data. Concrete data turns abstract expectations into repeatable checks.

```txt
Scenario: Registered user checks out an available book

Given book "Great book" is available
And user "Sam" is registered
When "Sam" checks out "Great book"
Then "Great book" is checked out by "Sam"
```

## Scenario Examination

After writing a scenario, examine it for missing or ambiguous requirements.

Questions to ask:

- What if the resource does not exist?
- What if the actor is not allowed to perform the action?
- What if the item is already in the target state?
- What business rule limits this action?
- What exact error should be visible?
- What data must be recorded?

These questions often produce additional scenarios.

## Declarative Style

Prefer declarative scenarios over imperative scripts. A declarative scenario says what behavior happens in domain terms. An imperative scenario lists low-level interaction steps.

Prefer:

```txt
When "Sam" checks out "Great book"
```

Avoid:

```txt
When "Sam" opens the search page
And types "Great book" into the search box
And clicks Search
And clicks the first result
And clicks Checkout
```

Use UI-level steps only when the UI journey itself is the acceptance behavior.

## Sources

- Wikipedia, "Acceptance test-driven development"
- Wikipedia, "Behavior-driven development"
- Cucumber documentation, "Behaviour-Driven Development"
