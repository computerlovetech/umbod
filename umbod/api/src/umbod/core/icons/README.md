# Icons

Reusable favicon discovery shared by connector kinds; orchestration depends on ports, while public HTTP adapters own network access.

- `models.py`: immutable requests, icons, and discriminated discovery outcomes. Icons accept credential-free HTTP(S) URLs and image data URLs for advertised icons. Endpoint URLs must be credential-free HTTP(S). HTTP discovery strategies must accept only HTTP(S) discovered URLs.
- `ports.py`: discovery and strategy contracts.
- `service.py`: ordered strategy batches, concurrent first-hit selection, configuration-order ties, strategy isolation, and overall deadlines. Unfinished tasks are cancelled and awaited before returning.
- `in_memory.py`: endpoint-keyed strategy results; unknown endpoints return not-found.
- `strategies.py`: first advertised icon selection without I/O.
- `http_models.py` and `http_ports.py`: validated HTTP requests, bounded-fetch policy, responses and unavailable results.
- `web_strategies.py`: origin `/favicon.ico` and HTML icon-link strategies. Hits require an image content type and a recognized image signature or SVG root. HTML candidates are bounded and resolved against the final document URL.
- `adapters/in_memory_http.py`: deterministic HTTP responses without network access.
- `adapters/http.py` and `adapters/network.py`: bounded streamed GETs, capped redirects and favicon URL policy. Public-IP validation, DNS pinning and pool configuration are shared through `umbod.core.network`. No credentials, cookies or environment proxies are used; compressed responses are rejected.
- `__init__.py`: public API exports.

Singleton batches execute sequentially; one batch executes concurrently. Timeouts must be positive and finite. Strategies must cooperate with cancellation; cleanup is awaited. Strategy failures log type information only, excluding endpoint and exception text.

Production connector wiring races the two website strategies directly. MCP-advertised icons remain owned by the MCP probe decorator; `AdvertisedIconStrategy` is available for custom discovery compositions.
