---
name: python-test-practices
description: >-
  Guides writing and organizing pytest-based Python tests with clear names,
  minimal fixtures, parametrization, edge-case coverage, and low runtime latency.
  Use when adding or refactoring tests, improving test layout or fixture reuse,
  profiling slow suites, or when the user mentions pytest, fixtures, test
  performance, or test quality.
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

## 5. Build just-enough fixtures and reuse safe setup

A fixture must supply only the setup the requesting test actually needs. Inspect its dependency graph, not only the arguments on the test function.

- Separate state, service, router, client, server registration and full-application fixtures. A test building its own server must not also request a prebuilt server. Pure error-mapping tests should not create databases or provision unrelated services.
- For HTTP or MCP boundary tests, compose the relevant real routes, adapters and security providers using existing production composition helpers. Do not copy substantial application wiring into tests.
- Retain explicit full-application integration tests for mounting, authentication, authorization, CSRF, middleware ordering, lifecycle, transport and error sanitization. An absent route is not evidence of an authorization denial.
- Keep mutable applications, clients, database runtimes, caller state, authorization caches, metrics, settings and environment overrides function-scoped. Cleanup must cover failure paths as well as successful tests.
- Reuse immutable expensive inputs at module or session scope when immutability is established: signing keys, static configuration and parsed immutable schemas. A frozen outer object does not make nested values immutable.
- Reuse worker-owned temporary-directory infrastructure with unique per-test paths where appropriate. Allocate a path separately from creating a file or database; do not request `tmp_path` or prepare storage for tests that do not use it.
- Avoid broad `autouse` fixtures unless every affected test needs the invariant. Keep unavoidable global isolation setup lightweight.
- Put shared fixtures in `conftest.py`; keep module-specific fixtures local. Reuse focused fixture composition rather than duplicating setup or making a catch-all fixture with many mode flags.
- Under xdist, module and session scope are per worker. Shared external resources still require explicit ownership and unique identities.

Do not broaden mutable fixture scope merely because setup is slow. Split reusable preparation from fresh per-test state instead.

---

## 6. Use fakes for external I/O dependencies

For units that depend on external I/O, use existing in-memory implementations or protocol-compatible fakes instead of real integrations. Business-logic tests should use the repository's in-memory persistence runtime, not SQLite or a new imitation of an existing adapter.

- Reuse existing adapters and fakes first. When none fits, write a small fake implementing the collaborator's protocol/ABC.
- Verify substitutable persistence implementations through the same parameterized contract tests. Do not duplicate business scenarios per backend.
- Retain explicit SQLite durability, migrations, encryption, concurrency, corruption and integration checks. Never bypass production durability requirements to make a fixture faster.
- Prefer fakes (stateful, behavior-preserving) over ad-hoc mocks when the test exercises interaction over many calls.
- Keep fakes in the test tree, next to the tests that use them, or in `conftest.py` when shared.
- When a focused test needs private patching, investigate whether the production code is missing a dependency-injection seam. Don’t add abstractions merely to eliminate mocks.

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

Keep parameter matrices tied to actual behavior. Avoid unnecessary Cartesian products and parent fixtures that multiply unrelated tests. Preserve meaningful boundaries, security cases, required backend contracts and supported configuration variants; do not sample away coverage merely to improve timings.

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

## 9. Measure runtime before optimizing

Treat low latency as a design constraint, not a reason to weaken assertions, isolation, coverage or production guarantees.

- Establish a baseline using the relevant suite, including its normal coverage and worker configuration. After changes, rerun the same selection and settings, and account for changed test counts.
- Use pytest durations to distinguish setup, calls and teardown. Slowest individual tests are not enough: aggregate fixture time and invocation counts to find inexpensive setup repeated hundreds of times.
- Profile the measured hot path before choosing a fix. Inspect application construction, provisioning, tool registration, database preparation and repeated subprocess work rather than assuming storage is responsible.
- Distinguish elapsed suite time from accumulated worker time. Nested fixture timings can overlap; never add them together as promised wall-clock savings.
- Inspect collection/startup, worker balance and the interval after the last test report. Do not attribute shutdown delays to coverage without evidence.
- Run focused checks serially to avoid worker startup overhead. Use the repository's capped parallel command for broad suites, and keep Kind/live-runtime tests serial. Do not run competing full suites while benchmarking or increase workers blindly.
- Report the command, pass/skip counts, elapsed time, coverage mode and worker count. Label local measurements as local; do not claim CI gains until measured there.
- Keep one-off profiling instrumentation and reports outside committed application and test code unless reusable tooling was requested.

---

## 10. Keep verification at the correct boundary

Keep standalone linting and static-analysis rule validation outside the default application pytest suite. Run these tools through their dedicated CLI or CI checks, not incidental pytest subprocess wrappers.

Application CLI behavior, process isolation, architecture contracts and genuine integration boundaries may still require subprocess tests. Preserve those checks; do not replace them with mocks solely to reduce runtime.

---

## Quick checklist

- [ ] New tests live in a file that matches the feature or layer under test, mirroring the source module layout.
- [ ] Test and class names state intent without reading the body.
- [ ] One primary behavior per test; helpers/fixtures hold shared setup.
- [ ] Every test, fixture, and helper has type-annotated parameters and return type.
- [ ] Shared fixtures live in `conftest.py`; module-specific fixtures stay in the test module.
- [ ] Fixture dependencies construct only resources exercised by the requesting test.
- [ ] Immutable preparation is reused; mutable applications, clients, persistence and caller state remain isolated.
- [ ] Fixtures own lifecycle and failure-path cleanup, including clients, runtimes, files and environment overrides.
- [ ] Business logic uses existing in-memory implementations; shared parameterized contracts and backend-specific integration checks remain intact.
- [ ] Narrow route fixtures reuse real composition helpers, with explicit full-application security and wiring coverage.
- [ ] Happy path plus at least one edge or error path where risk warrants it.
- [ ] Repetitive scenarios — including equivalent behavior across substitutable implementations — use `parametrize` instead of copy-paste.
- [ ] Parameter matrices cover meaningful differences without multiplying unrelated scenarios.
- [ ] Runtime changes have comparable before/after measurements; aggregate fixture costs are not presented as wall-clock savings.
- [ ] Standalone static-analysis tools are not executed as part of the application pytest suite.

After substantive test changes, run the relevant focused pytest target serially, then the applicable broader checks using the repository's documented commands. Preserve normal coverage during performance comparisons.
