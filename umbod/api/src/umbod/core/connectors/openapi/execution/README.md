# OpenAPI execution

`service.py` compiles approved operations and runs authentication, outbound transport, and response normalization through the shared execution pipeline. Authentication and normalization exceptions are internal failures. Only typed outbound transport failures identify downstream OpenAPI failures; arbitrary transport exceptions remain internal. Exceptions are re-raised unchanged until the existing public result sanitization.

`http_adapters.py` enforces destination, redirect, header, and response-size policies. Typed HTTP client exceptions are captured as safe invocation evidence before mapping to stable outbound error codes. The service preserves this original evidence. HTTP error status responses remain successful transport results in the public execution contract. MCP delivery telemetry independently classifies HTTP statuses >=400 as failed tool invocations; HTTP 2xx/3xx remain telemetry successes.

`authentication.py` supplies trusted authorization separately from caller request values. Failure evidence contains exception types and frame locations, never messages, source lines, or local values. The shared invocation pipeline owns evidence isolation and delivery telemetry owns completion recording.
