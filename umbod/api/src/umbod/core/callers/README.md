# Callers

**Module responsibility:** Immutable, transport-neutral caller observations and the caller-context provider port.

- `models.py`: authentication provenance, subject and declared-issuer observations, explicit unavailable states, required-field caller context and separate required-field `GroupMembership` observations.
- `ports.py`: synchronous `CallerContextProvider.get_context` contract.
- `__init__.py`: public contracts.

REST and MCP adapters supply provenance from their actual authentication composition, never user-submitted claims. Known built-in upstream verifiers, local simulation, semantic development verification and local test providers remain distinguishable. Arbitrary host-supplied authentication is deployment-established rather than automatically upstream-verified. These values describe the accepted authentication boundary; they neither verify tokens nor prove a human identity or authorization.

Subject and declared issuer strings are retained exactly, including legacy empty subject strings. Missing or non-string claims are unavailable observations, not new authentication rejection rules. Unavailable issuer does not distinguish an absent claim from a malformed claim; feature identity policies that require that distinction must retain their existing boundary validation. These observations must not replace canonical-owner mapping or its issuer-presence checks.

`GroupMembership.group_ids` is a required tuple of observed group IDs in a frozen model, separate from `CallerContext`. It neither qualifies those IDs nor proves membership authority; delivery-specific legacy capture policies retain their own filtering, coercion and ordering semantics. No caller context or membership is cached across MCP requests.

Tokens, arbitrary claims, profiles, framework objects, session IDs and group assertions are excluded from `CallerContext`. Identity/group authority mapping remains explicit feature policy. In particular, downstream personal `CanonicalPrincipal.namespace` is not necessarily a token issuer, Entra canonical subjects can differ from `sub`, and current group projections have deliberately different parsing rules. No filesystem principal can be inferred from this context without its own accepted mapping contract.

REST retains immutable observations on request state after successful authentication and administrator membership checks where applicable. MCP providers read the current SDK token per call and never cache callers across requests. An SDK token inherited or supplied by a host without a known built-in provider is classified as deployment-established; absent SDK authentication produces an unavailable caller. These contracts import no transport, infrastructure, configuration or connector-kind modules.
