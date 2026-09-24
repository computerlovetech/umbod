---
name: ports-adapters-io
description: >-
  Applies hexagonal (ports and adapters) design for I/O boundaries—network,
  files, databases—so the core stays independent of infrastructure. Use when the
  user mentions ports and adapters, hexagonal architecture,
  or any implementations for external I/O.
---

# Ports and Adapters for I/O

## Concept (source)

**Hexagonal architecture** (also **ports and adapters**) structures the system so the application core talks to the outside world only through **ports** (abstract APIs / protocols) implemented by **adapters** (HTTP clients, DB drivers, filesystem, tests). Components stay loosely coupled and swappable; multiple adapters can satisfy one port (for example GUI, CLI, or automated tests). See [Hexagonal architecture (software)](https://en.wikipedia.org/wiki/Hexagonal_architecture_(software)) on Wikipedia for the full pattern.

For **HTTP clients in this repo**, apply the same workflow using the concrete layout in [api-client-architecture](../api-client-architecture/SKILL.md) (Zod schemas, transport port, route classes, composite client).

## When to use

- Adding or changing code that performs **network**, **file**, or **database** I/O.
- The user or agent mentions **ports and adapters**, **hexagonal** architecture, or **adapter** / **port** in an I/O context.
- The user explicitly invokes this skill.

## Mandatory workflow

Follow this order every time. Do not skip steps.

### 1. Define the port first (interface / protocol)

- Name and shape the port from the **domain** need: what operation does the core require, independent of HTTP, SQL, or paths?
- Express inputs and outputs only as **domain-level** contracts at the boundary (see step 2).
- The port is an abstract type: Python `Protocol` or `ABC`, TypeScript `interface`, or an equivalent boundary the core depends on.

### 2. Validate at the boundary with Pydantic or Zod

- **Python**: Use Pydantic `BaseModel` (or equivalent) for every argument bundle and return value that crosses the port from or to the outside world. Parsing/validation happens in adapters (or immediately inside the port implementation that wraps raw bytes/rows).
- **TypeScript**: Use Zod schemas as the source of truth for wire and external shapes; derive types with `z.infer`. Do not hand-write parallel interfaces for the same payloads.
- The core should consume **already-validated** domain types where practical; adapters own mapping from raw I/O → validated models.

### 3. First adapter is always in-memory

- Ship an **in-memory** implementation of the port before (or alongside) the real network / file / DB adapter.
- It must satisfy the same interface and use the same Pydantic/Zod types so callers cannot tell which adapter they use.
- Use it for fast tests, local development, and proving the port shape before wrestling infrastructure.

### 4. Tests target the port, not implementation details

- Write tests **against the port contract**: call the public operations with validated inputs; assert on validated outputs and required error behavior.
- Do not assert on SQL strings, internal HTTP URLs, private methods, or file paths unless a dedicated adapter test exists for that adapter only.
- Prefer testing the **in-memory** adapter for business rules that flow through the port; add **narrow** tests for real adapters only for infrastructure concerns (connection config, query shape where untyped, etc.).

## Checklist before finishing I/O work

- [ ] Port defined from domain vocabulary; core imports only the port, not concrete drivers.
- [ ] Inputs/outputs at the boundary use Pydantic (Python) or Zod (TypeScript); invalid data fails at the edge.
- [ ] In-memory adapter implemented and used from tests or app wiring.
- [ ] Primary tests run through the port using the in-memory adapter; no coupling to transport specifics in those tests.

## Minimal examples

### Python: port → Pydantic → in-memory → test against port

```python
from typing import Protocol
from pydantic import BaseModel

class UserRecord(BaseModel):
    id: str
    name: str

class UserStore(Protocol):
    def get_user(self, user_id: str) -> UserRecord | None: ...

class InMemoryUserStore:
    def __init__(self) -> None:
        self._rows: dict[str, UserRecord] = {}

    def get_user(self, user_id: str) -> UserRecord | None:
        return self._rows.get(user_id)

    def seed(self, row: UserRecord) -> None:
        self._rows[row.id] = row

# Tests import UserStore and InMemoryUserStore only; assert behavior of get_user.
```

A real adapter (Postgres, REST, filesystem) implements `UserStore`, maps raw I/O into `UserRecord`, and is tested separately if needed.

### TypeScript: port → Zod → in-memory

```ts
import { z } from 'zod';

const UserRecord = z.object({ id: z.string(), name: z.string() });
type UserRecord = z.infer<typeof UserRecord>;

export type UserStore = {
  getUser(userId: string): Promise<UserRecord | null>;
};

export class InMemoryUserStore implements UserStore {
  private rows = new Map<string, UserRecord>();
  async getUser(userId: string) {
    return this.rows.get(userId) ?? null;
  }
  seed(row: UserRecord) {
    this.rows.set(row.id, UserRecord.parse(row));
  }
}

// Tests: instantiate InMemoryUserStore, call getUser, assert results — no fetch.
```

## Relation to other skills

- **HTTP / frontend API clients**: Follow [api-client-architecture](../api-client-architecture/SKILL.md) for Zod-at-the-transport and route layout.
- **Python tests**: Prefer interface-level examples in tests per [python-test-practices](../python-test-practices/SKILL.md).

## Anti-patterns

- Starting with a concrete `requests.get`, `open()`, or `cursor.execute` and “extracting an interface later”.
- Untyped `dict` / `Any` / `unknown` crossing the boundary without Pydantic/Zod.
- Skipping the in-memory adapter and testing only against live I/O (slow, flaky, unclear domain failures).
- Unit tests that break when the storage path or SQL dialect changes but the observable behavior did not.
