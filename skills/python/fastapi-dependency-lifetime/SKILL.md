---
name: fastapi-dependency-lifetime
description: Use when adding or modifying FastAPI routes, dependency providers, application services, repositories, adapters, app factories, lifespan setup, or any API object creation and dependency injection.
---

# FastAPI dependency lifetime

Create dependencies at the narrowest safe lifetime. Default to request-scoped application objects and reserve ASGI lifespan state for shared infrastructure resources that are designed for concurrent reuse.

## Core rule

Application services, repositories, use-case classes, handlers, dispatchers, and objects that perform operations on data must be created through FastAPI dependency providers during the request cycle by default.

ASGI lifespan and `app.state` are only for long-lived infrastructure resources with documented concurrency safety, such as database engines, database connection pools, shared HTTP client pools, telemetry clients, and explicitly safe SDK clients.

## Do not

- Do not use `app.state` as a general dependency container.
- Do not attach application services, repositories, use cases, handlers, or dispatchers to `app.state`.
- Do not instantiate request-operation objects in `api/main.py`.
- Do not share mutable service instances across async requests unless the type is explicitly designed for concurrent reuse.
- Do not resolve normal service dependencies with repeated `request.app.state.<service>` lookups.

## Do

- Keep `api/main.py` focused on app assembly, middleware, routers, exception handlers, mounts, and lifespan wiring.
- Put dependency provider functions near their bounded context, usually in a `deps.py` module.
- Use typed `Depends` providers to construct services, repositories, and use cases per request.
- Inject lifespan-owned infrastructure resources into request-scoped operation objects.
- Store only concurrency-safe infrastructure resources on `app.state` when FastAPI owns their lifecycle.
- Prefer explicit provider function chains over dynamic framework-state service lookup.

## Lifetime guide

### Lifespan-created

Create these in ASGI lifespan when the app owns their startup and shutdown:

- database engines
- database connection pools
- shared HTTP client pools
- shared SDK clients with documented thread or async safety
- telemetry and metrics exporters
- caches explicitly designed for concurrent shared access

### Request-created

Create these through FastAPI dependency providers:

- application services
- domain or application use cases
- repositories wrapping a pool, engine, client, or session
- notification dispatchers
- command and query handlers
- objects that coordinate reads, writes, validation, or data operations

## Preferred shape

```python
from typing import Annotated

from fastapi import Depends, Request


async def get_database_pool(request: Request) -> DatabasePool:
    return request.app.state.database_pool


async def get_booking_repository(
    pool: Annotated[DatabasePool, Depends(get_database_pool)],
) -> BookingRepository:
    return BookingRepository(pool)


async def get_booking_service(
    repository: Annotated[BookingRepository, Depends(get_booking_repository)],
) -> BookingService:
    return BookingService(repository)
```

`app.state.database_pool` is acceptable when the pool is concurrency-safe and lifecycle-owned by FastAPI. `app.state.booking_service` is not acceptable by default because the service performs request operations and may accumulate state or hide concurrency hazards.

## Review checklist

Before adding or moving object creation, answer these questions:

- Is this object documented as concurrency-safe and intended to be shared?
  - If yes, it may belong in lifespan or `app.state`.
  - If no or unclear, create it through `Depends`.
- Does the object hold request-specific data, mutable state, or operation coordination?
  - If yes, create it through `Depends`.
- Is this an application service, repository, use case, handler, or dispatcher?
  - If yes, create it through `Depends` by default.
- Is this being added to `api/main.py`?
  - If yes, reconsider and prefer bounded-context dependency providers.
- Are tests forced to patch `app.state` to replace an operation object?
  - If yes, move that object behind a typed provider that can be overridden.
