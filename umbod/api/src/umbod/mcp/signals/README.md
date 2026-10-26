# MCP signals

App-scoped typed events separate tool execution from concrete listeners.

- `events.py`: immutable invocation and inventory contracts.
- `context.py`: canonical invocation context and its single context variable.
- `diagnostics.py`: canonical invocation-local failure diagnostic context.
- `lifecycle.py`: shared start context and monotonic completion timing.
- `channels.py`: typed channels and guarded lifecycle failure reporting.
- `publisher.py`: best-effort lifecycle publication, at most one completion per lifecycle, and inventory publication without fake completions.
- `execution.py`: pipeline factory protocol, signal factory and connector execution interceptor.

Concrete log, metric and audit adapters are centrally wired in `../listeners/registration.py`. Inventory initialization is idempotent through the metric recorder and does not execute tools.
