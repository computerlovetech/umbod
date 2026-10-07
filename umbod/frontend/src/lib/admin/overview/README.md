# Admin Overview

**Module responsibility:** Read-only administration counts with explicit availability per connector family and tool subtotal.

## Modules

- `models.ts`: Validated source records and overview count contracts.
- `port.ts`: Source interface for connector lists, tool activations and registered permission groups.
- `in-memory-source.ts`: Validated in-memory source for interface-level tests.
- `api-source.ts`: Existing validated administration API adapter; operational failures become unavailable data, authorization and validation failures propagate.
- `aggregate.ts`: Independent source aggregation and globally bounded tool requests across all connector families.
- `aggregate.test.ts`: Public source-port aggregation coverage.

Successful empty lists yield zero. A failed connector list invalidates totals requiring that list. A failed tool request invalidates its family tool subtotal and the combined tool total, not connector counts. MCP configured counts mean saved proxies; unknown discovery is not unhealthy.
