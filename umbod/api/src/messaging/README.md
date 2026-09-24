# Messaging

**Module responsibility:** Shared event models and messaging ports used for communication between Umbod processes.

**Read when working with:** Event definitions, publishing, subscriptions, checkpoints, proxies, or in-memory and no-op transports.

## Modules

### `events.py` and `models.py`

**Read when working with:** Event payloads, envelopes, cursors, or shared messaging data.

### `ports.py`

**Read when working with:** Messaging contracts implemented or consumed by other modules.

### `in_memory.py` and `no_op.py`

**Read when working with:** Local, test, or disabled messaging behavior.

### `proxies.py`

**Read when working with:** Deferred messaging bindings and process-level adapter assembly.
