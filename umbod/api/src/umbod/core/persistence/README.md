# Persistence kernel

Backend-neutral persistence contracts shared by bounded-context stores. Drivers and composition live under `umbod/infrastructure/persistence/`; bounded contexts own their schemas, codecs and query builders.

- `ports.py`: immediate `Database`, `DatabaseSchema`, `DatabaseSession` and transaction-mode contracts.
- `query.py`: typed table/schema descriptors, codecs, predicates, projections, ordering and boundary validation.
- `runtime.py`: application-scoped runtime and readiness contracts.
- `plan.py`: deferred read registration through `ReadPlanOperations`, implemented by `ReadPlan`; typed `ManyRead` and `OneRead` handles and `ReadResults`.
- `__init__.py`: public kernel exports.

## Deferred reads

`ReadPlan()` registers validated queries without I/O using `find_many(table, query)` and `find_one(table, query)`. Handles retain the query result type. `await plan.execute(session)` uses only the supplied `DatabaseSession`, without opening a session or exposing writes. `results.get(many_handle)` returns a tuple; `results.get(one_handle)` returns a row or `None`. Foreign-plan handles raise `ValueError`.

Execution freezes registration, including when execution fails or is cancelled. Further registration raises `RuntimeError`. Frozen plans may execute repeatedly; every execution performs fresh reads and produces independent results. Failures and cancellation propagate without returning partial results.

A separate pure optimization phase deduplicates only structurally equal reads, comparing the complete table/schema descriptor, cardinality, projection/result type, predicate, ordering and limit without hashing descriptors. Execution runs the resulting reads in registration order. No arbitrary query coalescing is performed: bulk reads must be explicit in bounded-context query builders. Existing immediate session APIs remain unchanged.
