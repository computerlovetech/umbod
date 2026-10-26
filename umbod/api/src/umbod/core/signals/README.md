# Signals

**Module responsibility:** App-scoped, synchronous typed event delivery with explicit receiver registration and isolated ordinary receiver failures.

## Entry modules

- `__init__.py` exposes the dispatcher, publisher and receiver contracts, failure handler contract, failure records, and in-memory failure handler.
- `ports.py` defines typed publishing, receiver callbacks, and failure handling contracts.
- `dispatcher.py` owns ordered named receiver registration and snapshot delivery without global registration or framework dependencies.
- `models.py` defines immutable receiver failure records.
- `in_memory.py` captures receiver failures through the failure handler contract.
