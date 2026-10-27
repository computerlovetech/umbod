# Key-value contract

- `models.py` defines frozen `KeyValueHit(value)` and `KeyValueMiss` results.
- `ports.py` defines the generic `KeyValueDriver` protocol.
- `__init__.py` exports the protocol and result models.

Drivers accept hashable keys and expose asynchronous get, set, delete, and clear operations.
A miss is explicit and distinct from a hit containing `None` or another falsy value.
Setting an existing key overwrites its value; deleting a missing key succeeds.
Clear removes only entries owned by that driver instance and is repeatable.

The contract does not provide expiration, serialization, distributed coordination,
thread safety, or request-load deduplication.
