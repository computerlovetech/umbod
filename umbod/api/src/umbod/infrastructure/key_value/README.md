# In-memory key-value infrastructure

- `inmemory.py` implements the core key-value port using one dictionary per driver.
- `factory.py` composes fresh drivers and request caches.
- `__init__.py` exports only `create_inmemory_key_value_driver` and `create_request_cache`.

The driver factory lazily imports the concrete implementation and returns the core
`KeyValueDriver` protocol. Every call creates independent storage.
The request-cache factory injects a fresh driver into the core `RequestCache`.

Hashable keys, including compound keys, retain normal Python dictionary equality
semantics. Values are held by reference without copying or serialization.
Missing keys return `KeyValueMiss`; stored values, including `None` and falsy
values, return `KeyValueHit`. Set overwrites, delete tolerates missing keys,
and clear is repeatable and scoped to one driver instance.

Operations are intended for a single event loop. No thread safety, cross-process
storage, or distributed guarantees are provided. No Redis driver is implemented.
