# ADR-002: Client-Owned Credentials for Multi-Provider MCP Tool Authentication

- **Status:** Proposed
- **Date:** 2026-09-26
- **Decision owners:** Architecture / Platform
- **Scope:** MCP gateway exposing tools backed by multiple independently authenticated services
- **Target implementation:** FastMCP-based gateway

## Decision

Design the single MCP gateway endpoint around client-owned OAuth credentials. The MCP client/host discovers authorization requirements, performs OAuth, persists and refreshes credentials, and presents the appropriate bearer token for each protected invocation.

The gateway resolves the tool's authorization policy, challenges missing or insufficient credentials, advertises Protected Resource Metadata, and validates issuer, resource/audience, scopes, expiry, and applicable token constraints. It uses only the current invocation's authorization context and never persists downstream access or refresh tokens.

Blind token forwarding is excluded. Forwarding requires explicit policy and a token valid for the downstream resource; otherwise delegation/token exchange or a different resource design is required. Credentials must remain isolated between issuers, resources, callers, and concurrent requests, and must not enter logs, traces, or other durable records.

## Context and rationale

Umbod wants one MCP endpoint aggregating local tools and downstream services with independently authenticated tool groups. Making the gateway an OAuth client for every provider would turn it into a long-lived credential vault.

Client ownership reduces persistent credential exposure and gateway custody obligations. It does not protect tokens passing through a compromised running gateway.

The proposal assumes target hosts can retain multiple issuer/resource authorization contexts behind one endpoint and handle challenges and scope step-up. Protocol or SDK capability alone does not establish host interoperability. Per-tool challenges may require HTTP middleware beyond FastMCP's server-wide authentication configuration.

## Alternatives considered

- **Gateway-stored refresh tokens:** straightforward integration and potentially consistent UX, but creates a high-value credential vault. Not preferred; may be necessary for incompatible clients/providers.
- **Gateway memory-only credentials:** avoids durable storage, but loses continuity when credentials disappear or expire. Rejected as the general solution.
- **One gateway identity with service credentials:** suitable when the gateway is the principal, but unsuitable when downstream permissions and audit identity must belong to the user.
- **Separate MCP endpoints per provider:** simpler OAuth configuration and potentially better client compatibility, but does not meet the desired single-endpoint interface. Primary fallback if interoperability is insufficient.

## Consequences

The client owns credential refresh and multi-provider OAuth state. Gateway storage compromise exposes fewer persistent credentials, and tool-specific scopes can support least privilege.

Compatibility and authorization UX depend on each host. The gateway still handles bearer tokens transiently, must enforce provider/resource isolation and redaction, and may need additional HTTP authorization routing. Forwarding remains conditional on each integration's OAuth resource semantics.

## Confidence and reevaluation

Confidence was not recorded. Acceptance remains conditional on tests with the actual target hosts: independent authorization to two providers, retained/refreshed credentials without cross-provider contamination, scope step-up, revocation behavior, FastMCP challenge hooks, correct token audience, and absence of tokens from persistent storage and telemetry.

The supported host set, metadata addressing, delegation requirements, and mid-workflow authorization UX remain unresolved. If the compatibility gate fails, revisit the separate-endpoint fallback before acceptance. After acceptance, a changed credential-ownership decision requires a new ADR.

## Supporting material

- [Proposed design, security requirements, open questions, and compatibility gate](supporting/client-owned-credentials.md)
- [RFC 9728: OAuth 2.0 Protected Resource Metadata](https://www.rfc-editor.org/rfc/rfc9728)
- [RFC 8707: Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
