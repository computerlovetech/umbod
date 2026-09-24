---
name: choose-design-pattern
description: >-
  Guides refactoring agents in choosing object-oriented design patterns from
  concrete code smells and architecture problems. Use when refactoring code that
  may benefit from patterns such as Factory Method, Strategy, State, Adapter,
  Facade, Decorator, Observer, Command, Composite, or related OO design patterns.
disable-model-invocation: true
---

# Design Pattern Decision Tree for Refactoring Agents

> Goal: match codebase symptoms to design-pattern refactoring candidates.
> Each pattern below can be selected or rejected in at most five decisions.

## How to Use This Guide

1. Start from a concrete code smell, not from a preferred pattern.
2. Identify the main unstable axis: creation, structure, behavior, state, traversal, or notification.
3. Follow the shortest matching branch.
4. Confirm the pattern removes repeated edits or unsafe coupling.
5. Reject the pattern when a smaller local refactor solves the issue.
6. When the decision has been made to use a specific pattern, read that pattern's reference file before proposing or implementing the refactor.

## Pattern Reference Files

Read the matching reference file after selecting a pattern:

- **Abstract Factory**: [references/abstract-factory.md](references/abstract-factory.md)
- **Adapter**: [references/adapter.md](references/adapter.md)
- **Bridge**: [references/bridge.md](references/bridge.md)
- **Builder**: [references/builder.md](references/builder.md)
- **Chain of Responsibility**: [references/chain-of-responsibility.md](references/chain-of-responsibility.md)
- **Command**: [references/command.md](references/command.md)
- **Composite**: [references/composite.md](references/composite.md)
- **Decorator**: [references/decorator.md](references/decorator.md)
- **Facade**: [references/facade.md](references/facade.md)
- **Factory Method**: [references/factory-method.md](references/factory-method.md)
- **Flyweight**: [references/flyweight.md](references/flyweight.md)
- **Iterator**: [references/iterator.md](references/iterator.md)
- **Mediator**: [references/mediator.md](references/mediator.md)
- **Memento**: [references/memento.md](references/memento.md)
- **Observer**: [references/observer.md](references/observer.md)
- **Prototype**: [references/prototype.md](references/prototype.md)
- **Proxy**: [references/proxy.md](references/proxy.md)
- **Singleton**: [references/singleton.md](references/singleton.md)
- **State**: [references/state.md](references/state.md)
- **Strategy**: [references/strategy.md](references/strategy.md)
- **Template Method**: [references/template-method.md](references/template-method.md)
- **Visitor**: [references/visitor.md](references/visitor.md)

## Root Triage

- Object creation is duplicated, conditional, or hard to configure: inspect **Creational Patterns**.
- Object relationships, wrappers, APIs, trees, or subsystem boundaries are awkward: inspect **Structural Patterns**.
- Algorithms, workflows, requests, notifications, or state-dependent behavior are tangled: inspect **Behavioral Patterns**.
- The smell is only naming, formatting, or one long method: refactor locally first.
- There is no recurring variation or coupling problem: avoid adding a pattern.

---

# Creational Patterns

## Factory Method

1. Do callers or base classes create concrete products behind a shared product interface?
2. Are `if`, `switch`, registry, or subclass checks choosing concrete product classes in several places?
3. Is there only one product type varying, rather than a whole compatible product family?
4. Is the product complete immediately after creation, without many ordered setup steps?
5. Choose **Factory Method**; otherwise consider **Abstract Factory**, **Builder**, or dependency injection.

## Abstract Factory

1. Does one environment, platform, theme, vendor, protocol, or mode determine several related product types together?
2. Must those products stay mutually compatible once selected?
3. Do clients currently know too many concrete classes from the same family?
4. Would adding a new family require coordinated edits across multiple product constructors?
5. Choose **Abstract Factory**; otherwise consider **Factory Method** for one product or **Bridge** for runtime delegation axes.

## Builder

1. Is one object hard to construct because it has many optional parts, validation rules, or ordered setup steps?
2. Do callers repeat step-by-step assembly before the object is usable?
3. Are telescoping constructors, large parameter objects, or boolean flags obscuring intent?
4. Is the variation about assembly rather than choosing a concrete product class?
5. Choose **Builder**; otherwise consider **Factory Method**, named constructors, or a simple constructor.

## Prototype

1. Are new objects usually variants of existing configured examples?
2. Is constructing the object from scratch verbose, expensive, or less natural than copying a template?
3. Can identity, ownership, and mutable fields be copied safely and predictably?
4. Do clients need runtime-defined examples rather than compile-time construction logic?
5. Choose **Prototype**; otherwise consider **Builder** or **Factory Method**.

## Singleton

1. Is exactly one instance a true domain or infrastructure constraint, not just a convenience?
2. Must access to that one instance be centralized across the process?
3. Would dependency injection or application lifecycle management fail to express the constraint clearly?
4. Can tests remain isolated without hidden mutable global state or order dependence?
5. Choose **Singleton** only if all answers are yes; otherwise prefer dependency injection or a managed service instance.

---

# Structural Patterns

## Adapter

1. Is useful code available but its interface does not match what the client expects?
2. Are clients repeating argument conversion, response mapping, method renaming, or exception translation?
3. Is the goal compatibility with one object or API shape, not simplifying a whole subsystem?
4. Can the original dependency remain unchanged because it is external, shared, or costly to modify?
5. Choose **Adapter**; otherwise change the interface directly or consider **Facade**.

## Bridge

1. Do class names or branches combine two independent variation axes, such as feature plus platform?
2. Does adding one variant require edits or subclasses across the other axis?
3. Can one axis be modeled as an abstraction and the other as an implementation delegate?
4. Must both axes vary independently at compile time or runtime?
5. Choose **Bridge**; otherwise consider **Strategy** for one algorithm axis or **Abstract Factory** for product-family creation.

## Composite

1. Do clients need to treat individual objects and groups of objects uniformly?
2. Is the domain naturally a tree, part-whole structure, menu, document, scene graph, or hierarchy?
3. Do operations recurse through children while doing similar work on leaves and containers?
4. Are leaf/container checks spread across clients?
5. Choose **Composite**; otherwise consider **Iterator** for traversal or **Visitor** for adding operations to an existing hierarchy.

## Decorator

1. Do objects need optional responsibilities around the same interface?
2. Are subclasses multiplying because feature combinations are being encoded as classes?
3. Can responsibilities be stacked independently, such as logging, validation, compression, formatting, caching, or policy checks?
4. Should clients still see the original interface after wrapping?
5. Choose **Decorator**; otherwise consider **Proxy** for access control or **Strategy** for one replaceable policy.

## Facade

1. Do many clients repeat the same choreography across several subsystem objects?
2. Are low-level subsystem details leaking into application code?
3. Is the goal a simpler entry point, not adapting one incompatible interface?
4. Can the facade expose cohesive use cases instead of becoming a dumping-ground service?
5. Choose **Facade**; otherwise consider **Adapter** for compatibility or **Mediator** for peer coordination.

## Flyweight

1. Are there very many similar small objects causing measurable memory pressure?
2. Can repeated immutable data be separated from per-use extrinsic state?
3. Can shared intrinsic state be safely reused without object identity or mutation surprises?
4. Can callers supply the extrinsic state at operation time?
5. Choose **Flyweight**; otherwise avoid it or consider **Prototype** when copying configured objects is the real need.

## Proxy

1. Should a stand-in control access to another object while exposing the same interface?
2. Are callers repeating lazy loading, permission checks, remote calls, retries, caching guards, or lifecycle checks?
3. Is the wrapper primarily controlling access rather than adding optional feature behavior?
4. Can the proxy remain transparent enough that clients do not depend on proxy-specific details?
5. Choose **Proxy**; otherwise consider **Decorator**, **Facade**, or direct access.

---

# Behavioral Patterns

## Chain of Responsibility

1. Does a request pass through an ordered set of potential handlers?
2. Can each handler decide to process, pass along, or stop the request?
3. Are long ordered conditionals currently selecting handlers?
4. Is the exact handler intentionally variable or unknown to the sender?
5. Choose **Chain of Responsibility**; otherwise consider **Command** for action objects or direct dispatch when the handler is known.

## Command

1. Must operations be represented as objects rather than immediate method calls?
2. Do actions need queuing, scheduling, logging, retrying, composing, remote execution, or undo?
3. Should the invoker be decoupled from the receiver that performs the work?
4. Can each command define clear inputs, side effects, and failure behavior?
5. Choose **Command**; pair with **Memento** when undo requires restoring captured state.

## Iterator

1. Do clients need traversal without knowing the collection representation?
2. Are loops depending on indexes, node links, storage fields, cursors, pages, or tree internals?
3. Should multiple traversal orders or lazy traversal be supported?
4. Can iteration rules be expressed clearly, including invalidation and ordering?
5. Choose **Iterator**; otherwise expose a simple native collection or consider **Composite** when modeling the tree is the real issue.

## Mediator

1. Do peer components know too much about each other?
2. Are many classes directly calling siblings with conditional workflow rules?
3. Is coordination more complex than simple publish-subscribe notification?
4. Can workflow decisions be centralized without creating a god object?
5. Choose **Mediator**; otherwise consider **Observer** for broadcasts or **Facade** for external subsystem simplification.

## Memento

1. Must previous object state be captured and restored later?
2. Is external code copying or exposing internal fields to support undo, rollback, or checkpoints?
3. Should only the originator understand the snapshot contents?
4. Are snapshot size, lifetime, and mutation safety manageable?
5. Choose **Memento**; otherwise consider **Command** for action history or event sourcing when events are the source of truth.

## Observer

1. Does one subject change while unknown or variable dependents need notification?
2. Is the subject directly calling many unrelated dependents after state changes?
3. Should multiple subscribers be able to react to the same event?
4. Can subscription lifecycle, ordering, and failure handling be made explicit?
5. Choose **Observer**; otherwise consider **Mediator** for coordinated workflows or **Chain of Responsibility** when one handler consumes a request.

## State

1. Does an object change behavior based on its lifecycle state?
2. Are repeated `if status == ...` or `switch state` blocks spread across several methods?
3. Do state transitions change which operations are valid or how they behave?
4. Would adding a state require edits in many conditional blocks?
5. Choose **State**; otherwise consider **Strategy** for externally selected policies or simple enum logic for data-only states.

## Strategy

1. Does one algorithm, rule, or policy vary independently from the object using it?
2. Are conditionals choosing pricing, validation, routing, sorting, ranking, formatting, or serialization behavior?
3. Is the choice external configuration or context, not an internal lifecycle transition?
4. Can all variants share one focused interface?
5. Choose **Strategy**; otherwise consider **State** for lifecycle behavior or **Template Method** when inheritance owns the fixed algorithm skeleton.

## Template Method

1. Do sibling classes share the same algorithm outline?
2. Do they differ only in selected steps, hooks, or primitive operations?
3. Is the step order stable and best owned by a base class?
4. Is inheritance already appropriate and unlikely to become a composition problem?
5. Choose **Template Method**; otherwise consider **Strategy** for runtime replacement or **Builder** for construction flow.

## Visitor

1. Is there a stable set of element classes but many operations need to be added over them?
2. Are operations currently implemented with type checks over a hierarchy or object graph?
3. Do new operations change more often than element classes?
4. Can double dispatch or equivalent dispatch be kept understandable?
5. Choose **Visitor**; otherwise consider **Composite** for representing the tree or methods on elements when element behavior changes often.