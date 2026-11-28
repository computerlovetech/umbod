---
type: Software Module
title: MCP authentication
description: Provider composition, explicit transport authentication, caller capture and OAuth presentation.
---

# Files

- [__init__.py](./__init__.py) — Public provider and transport authentication contracts.
- [agent_tokens.py](./agent_tokens.py) — Public MultiAuth composition and trusted agent credential provenance.
- [caller.py](./caller.py) — Capture authenticated caller identity from the current MCP token.
- [client_storage.py](./client_storage.py) — Encrypted storage for OAuth client registration.
- [consent_screen.py](./consent_screen.py) — Consent presentation and FastMCP UI integration.
- [debug_middleware.py](./debug_middleware.py) — Allowlisted authentication-presence diagnostics.
- [factory.py](./factory.py) — Configured provider construction.
- [groups.py](./groups.py) — Capture administrator membership from token claims.
- [local_test_auth.py](./local_test_auth.py) — Single-test-user OAuth provider.
- [membership.py](./membership.py) — Binds human mappings or instance-checked agent grants to the current MCP message.
- [transport.py](./transport.py) — Explicit authenticated and unauthenticated transport choices.
