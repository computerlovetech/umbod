---
name: python-test-practices
description: >-
  Guides writing and organizing pytest-based Python tests with clear names,
  fixtures, parametrization, and edge-case coverage. Use when adding or
  refactoring tests, improving test layout, naming test functions, splitting
  large tests, or when the user mentions pytest, fixtures, or test quality.
---

# Python test practices (pytest)

Follow these practices when writing or changing Python tests in this repository (and similar projects using pytest).

## 1. Organize tests by functionality

Split tests into **separate modules** by what they exercise (feature, layer, or subsystem), not one giant file.

**Do:** mirror the test folder layout to the source module layout.

For the `api/` package that means:

- source: `api/src/agent_backend/agent/tools/...`
- test:   `api/tests/agent/tools/...`

```text
tests/
  test_api_events.py           # HTTP event listing routes
  test_http_api_client_crud.py # CLI HTTP client against ASGI
  test_instance_service.py     # service layer
  stores/
    test_stores.py             # store implementations
```

**Avoid:** dumping unrelated scenarios into a single `test_everything.py`.

---

## 2. Use descriptive test names

Names should read as a **spec**: *under what condition*, *what happens*. Prefer full words over abbreviations.

**Good:**

- `test_get_domain_missing_returns_404`
- `test_list_domains_empty`
- `test_create_entity_type_rejects_duplicate_name_in_same_domain`

**Weak:**

- `test_domains_1`
- `test_error`

Group related names with **classes** (`TestDomainsGet`, `TestDomainsPatch`) when it keeps files scannable.

---

## 3. Keep tests small and focused

Each test should verify **one behavior** (one logical outcome). Share setup via helpers or fixtures, not by chaining many unrelated asserts in one test.

**Do:** arrange → act → assert on that outcome only.

```python
def test_patch_domain_updates_display_name(httpx_api: HttpxAgentBackendApi) -> None:
    created = _new_domain(httpx_api, "Alpha", "first")
    r = httpx_api.patch_domain(created["id"], {"display_name": "Beta"})
    assert r.status_code == 200
    assert r.json()["display_name"] == "Beta"
```

**Avoid:** one test that creates, lists, gets, patches, deletes, and asserts fifteen different things.

Use **private factory helpers** (e.g. `_new_domain`) only to return ready-made data; keep assertions in the test body.

---

## 4. Type tests explicitly

Tests are code and follow the same typing standards as production code.

- Annotate **every** test function signature, including the return type (usually `-> None`).
- Annotate **every** fixture signature, including its return/yield type.
- Annotate **every** parameter a test receives from a fixture; don't rely on pytest discovering it untyped.
- Type private helpers (`_new_domain`, `_domain_and_type`, ...) the same way you'd type any other function.

**Good:**

```python
@pytest.fixture
def httpx_api() -> HttpxAgentBackendApi:
    ...


def test_list_domains_empty(httpx_api: HttpxAgentBackendApi) -> None:
    assert httpx_api.list_domains().json() == []
```

**Avoid:** untyped `def test_foo(httpx_api):` — the fixture dependency and the test contract should both be readable from the signature alone.

---

## 5. Use fixtures for shared resources

Use **`@pytest.fixture`** for setup/teardown that many tests need: app + client, temp dirs, DB session, env overrides. Prefer **function scope** unless a slower resource truly needs session scope.

**Where fixtures live:**

- Put a fixture in `conftest.py` when it is shared across **multiple** test modules.
- Keep a fixture inside the test module when it is tightly coupled to that **single** module.

**Example (API client + ASGI app):**

```python
# tests/conftest.py
import pytest
from starlette.testclient import TestClient

from agent_backend.app import create_app
from agent_backend.cli.client import HttpClientManager
from agent_backend.cli.http_api import HttpxAgentBackendApi
from agent_backend.settings import APISettings, StoreType


@pytest.fixture
def httpx_api() -> HttpxAgentBackendApi:
    settings = APISettings(store_type=StoreType.INMEMORY)
    app = create_app(settings)
    base = f"http://test{settings.api_path_prefix}"
    with TestClient(app, base_url=base, headers={...}) as transport:
        manager = HttpClientManager(base, http_client=transport)
        yield HttpxAgentBackendApi(manager)
        manager.close()
```

**Do:** yield fixtures for cleanup after the test. **Avoid:** global mutable state without a reset strategy between tests.

---

## 6. Use fakes for external I/O dependencies

For units that depend on network, filesystem, database, or other external I/O, substitute **fake class implementations** (or equivalent test doubles) instead of hitting real integrations.

- Write small, hand-rolled fakes that implement the same protocol/ABC as the real collaborator.
- Prefer fakes (stateful, behavior-preserving) over ad-hoc mocks when the test exercises interaction over many calls.
- Keep fakes in the test tree, next to the tests that use them, or in `conftest.py` when shared.

**Good:**

```python
class FakeEntityStore(EntityStore):
    def __init__(self) -> None:
        self._by_id: dict[str, Entity] = {}

    def get(self, entity_id: str) -> Entity | None:
        return self._by_id.get(entity_id)

    def put(self, entity: Entity) -> None:
        self._by_id[entity.id] = entity


def test_service_returns_none_for_missing_entity() -> None:
    service = EntityService(store=FakeEntityStore())
    assert service.get("missing") is None
```

**Avoid:** talking to real HTTP servers, real databases, or the real filesystem from unit tests.

---

## 7. Test edge cases and bad input

Add tests for **boundaries and failure paths**: empty collections, missing IDs, invalid payloads, duplicate creates, wrong parent resource.

**Examples:**

- List when nothing exists → `[]` and 200.
- `GET` / `PATCH` / `DELETE` on missing id → `404`.
- Invalid body → `400` or `422` as documented by the API.
- Patch with unknown fields or empty object when the API forbids it.

```python
def test_patch_instance_empty_payload_returns_400(httpx_api: HttpxAgentBackendApi) -> None:
    domain_id, type_id = _domain_and_type(httpx_api)
    inst = httpx_api.create_instance(domain_id, type_id, {"title": "x"}).json()
    r = httpx_api.patch_instance(domain_id, type_id, inst["id"], {})
    assert r.status_code == 400
```

---

## 8. Use parametrized tests for multiple inputs

Use **`@pytest.mark.parametrize`** when the same behavior must hold for several values; keep the test body identical, vary only inputs and expected fragments.

```python
import pytest


@pytest.mark.parametrize(
    "raw,expected_fragment",
    [
        ("", "empty"),
        ("   ", "whitespace"),
        ("a" * 10_000, "length"),
    ],
)
def test_validate_slug_rejects_invalid_values(raw: str, expected_fragment: str) -> None:
    with pytest.raises(ValueError, match=expected_fragment):
        validate_slug(raw)
```

**Do:** parametrize **data**; use separate tests when **setup** or **assertions** differ materially.

**Also use parametrize to verify equivalent behavior across substitutable implementations** (for example, an in-memory store vs. a SQLite-backed store) so one test body exercises both, rather than copy-pasting the scenario per implementation.

```python
@pytest.mark.parametrize(
    "store_factory",
    [InMemoryEntityStore, SqliteEntityStore],
    ids=["inmemory", "sqlite"],
)
def test_store_roundtrips_entity(store_factory: Callable[[], EntityStore]) -> None:
    store = store_factory()
    store.put(Entity(id="a", title="t"))
    assert store.get("a") == Entity(id="a", title="t")
```

---

## Quick checklist

- [ ] New tests live in a file that matches the feature or layer under test, mirroring the source module layout.
- [ ] Test and class names state intent without reading the body.
- [ ] One primary behavior per test; helpers/fixtures hold shared setup.
- [ ] Every test, fixture, and helper has type-annotated parameters and return type.
- [ ] Shared fixtures live in `conftest.py`; module-specific fixtures stay in the test module.
- [ ] Fixtures own lifecycle (especially clients, files, env).
- [ ] External I/O (network, filesystem, DB) is replaced with a fake or equivalent test double.
- [ ] Happy path plus at least one edge or error path where risk warrants it.
- [ ] Repetitive scenarios — including equivalent behavior across substitutable implementations — use `parametrize` instead of copy-paste.

After substantive test changes, run the relevant pytest target (e.g. `uv run pytest tests/<file> -q` from the package root).
