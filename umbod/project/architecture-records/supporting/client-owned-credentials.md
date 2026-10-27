# Client-owned credentials — supporting design

Preserved design detail from [ADR-002: Client-Owned Credentials for Multi-Provider MCP Tool Authentication](../ADR-002-client-side-credential-storage.md). This remains proposed, not an implementation authorization or evidence of client compatibility. The original MCP/SDK references below do not identify exact versions or source links; their claims still require verification against the selected clients and protocol version.

## Authentication Model

### Authentication is associated with tool/resource policy

The gateway maintains an authorization policy for exposed tools.

Conceptually:

``` text
Tool namespace       Authorization server / policy
--------------------------------------------------------
internal_*           https://auth.example.com
service_a_*          https://auth.service-a.example
service_b_*          https://auth.service-b.example
public_*             none
```

The mapping does not necessarily need to be based on naming. It should
preferably be explicit metadata/configuration associated with the
mounted or proxied tool set.

For example:

``` python
tool_auth = {
    "internal_search": InternalAuthPolicy,
    "service_a_search": ServiceAAuthPolicy,
    "service_a_create": ServiceAAuthPolicy,
    "service_b_query": ServiceBAuthPolicy,
}
```

Namespaces are useful because they make the security boundary visible
and reduce accidental routing ambiguity, but namespace strings must not
themselves be treated as the authorization control.

## Authorization Flow

### 1. Client discovers the tool

The client connects to:

``` text
https://gateway.example.com/mcp
```

The server exposes tools such as:

``` text
internal_search
service_a_search
service_a_create
service_b_query
```

Tool discovery itself may be public or protected according to gateway
policy.

### 2. Client invokes a protected tool without the required authorization

For example:

``` text
tools/call service_a_search
```

The gateway determines that `service_a_search` requires authorization
associated with Service A.

No acceptable credential is present.

The gateway responds at the HTTP authorization boundary with a
`401 Unauthorized` challenge containing a `WWW-Authenticate` reference
to the applicable Protected Resource Metadata.

Conceptually:

``` http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer resource_metadata="https://gateway.example.com/.well-known/..."
```

### 3. Client discovers authorization requirements

The MCP client retrieves the referenced Protected Resource Metadata.

That metadata identifies the authorization server and relevant
resource/scopes.

Conceptually:

``` json
{
  "resource": "https://gateway.example.com/...",
  "authorization_servers": [
    "https://auth.service-a.example"
  ],
  "scopes_supported": [
    "search",
    "create"
  ]
}
```

The exact metadata structure and resource identifiers are
implementation- and protocol-version-sensitive and must follow the MCP
authorization specification used by the selected clients.

### 4. Client performs OAuth

The MCP client/host performs the authorization flow against Service A's
authorization server.

``` text
MCP Client
    |
    +------ authorization request ------> OAuth A
    |                                      |
    |<---------- user consent -------------+
    |
    |<--------- authorization code --------+
    |
    +---------- token exchange ----------->+
    |
    |<------ access / refresh tokens -------+
```

Crucially, the resulting refresh token is stored by the **client**, not
the gateway.

### 5. Client retries the invocation

The client retries the MCP request with the appropriate access token.

``` http
Authorization: Bearer <service-a-access-token>
```

### 6. Gateway validates the token

Before the tool executes, the gateway validates at least:

``` text
signature
issuer
resource / audience
expiration
required scopes
applicable token-binding requirements
```

A token accepted for one authorization domain must not automatically be
accepted for another.

For example:

``` text
token issued by OAuth A

        OK
         |
         v
service_a_search

        X
         |
         v
service_b_query
```

### 7. Gateway invokes the downstream service

If the downstream service accepts the same access token and the token is
valid for that downstream resource, the gateway may forward it for that
invocation.

``` text
MCP Client
    |
    | Bearer A
    v
Gateway
    |
    | Bearer A
    v
Downstream MCP A
```

The gateway holds the token only for the lifetime necessary to process
the request.

It must not write it to:

-   application databases,
-   caches intended to survive the request,
-   logs,
-   traces,
-   error reports,
-   analytics systems,
-   task snapshots,
-   message queues unless an explicitly designed secure delegation
    mechanism requires it.

## Important Constraint: Token Audience and Resource Binding

Blind bearer-token forwarding is **not** part of this decision.

An access token issued for the gateway is not automatically valid for a
downstream MCP server.

For example:

``` text
Token:

issuer   = https://auth-a.example
audience = https://gateway.example.com

                         valid
                           |
                           v
                    MCP Gateway

                           X
                           |
                           v
                    Downstream MCP A
                    https://mcp-a.example
```

The gateway may forward a token only when the authorization design
intentionally makes that token valid for the downstream resource.

Otherwise, a standards-based delegation/token-exchange mechanism or a
different resource design is required.

This must be established independently for every downstream integration.

## Multiple Authorization Servers

The architecture assumes that the MCP client can maintain credentials
for multiple authorization servers and select or reacquire the correct
authorization context when challenged.

Conceptually:

``` text
MCP Client Credential Store

+-------------------------------------+
| issuer: auth.internal.example       |
| access token                        |
| refresh token                       |
+-------------------------------------+

+-------------------------------------+
| issuer: auth.service-a.example      |
| access token                        |
| refresh token                       |
+-------------------------------------+

+-------------------------------------+
| issuer: auth.service-b.example      |
| access token                        |
| refresh token                       |
+-------------------------------------+
```

Credentials must remain isolated by authorization-server issuer and
resource context.

Current MCP SDK work explicitly supports issuer-bound OAuth credentials.
Implementations capable of holding credentials for several authorization
servers can key storage by issuer.

However, **support in the specific MCP hosts we intend to support must
be verified**. Protocol capability does not guarantee that every host
provides the same multi-provider UX or correctly handles multiple
authorization contexts behind one MCP endpoint.

This is therefore an implementation acceptance criterion rather than an
assumption.

## Scope Step-Up

Different tools belonging to the same authorization domain may require
different scopes.

For example:

``` text
service_a_search
    requires: service-a:read

service_a_create
    requires: service-a:write
```

A client may initially possess:

``` text
service-a:read
```

and later invoke:

``` text
service_a_create
```

The gateway should reject the insufficient authorization using the
protocol-defined insufficient-scope mechanism. The client can then
perform scope step-up and retry.

This keeps least-privilege authorization possible without requiring the
gateway to manage credentials.

## FastMCP Gateway Responsibilities

FastMCP is used as the MCP implementation layer, but authorization
policy belongs at the HTTP/resource boundary as well as in the tool
implementation.

A conceptual request pipeline is:

``` text
HTTP /mcp
    |
    v
Identify MCP operation/tool
    |
    v
Resolve ToolAuthPolicy
    |
    +-- public ----------------------------+
    |                                     |
    +-- protected                         |
            |                             |
            v                             |
      Extract bearer token                |
            |                             |
            +-- missing --> 401 challenge |
            |                             |
            v                             |
      Validate token                      |
            |                             |
            +-- invalid --> 401           |
            |
            +-- insufficient scope --> authorization
            |                              challenge
            v
      Create AuthContext
            |
            +-----------------------------+
                          |
                          v
                    FastMCP tool
                          |
                          v
                 downstream adapter
```

The tool handler should receive an already validated authorization
context.

Defence-in-depth checks may additionally be performed in the handler,
but the handler should not be the first authorization boundary.

## Downstream Adapter

Each proxied MCP should be represented by an adapter with an explicit
authentication policy.

Conceptually:

``` python
class DownstreamMCP:
    endpoint: str
    auth_policy: AuthPolicy

    async def call(self, tool, arguments, auth_context):
        credential = auth_policy.credential_for(auth_context)

        return await downstream.call_tool(
            tool,
            arguments,
            credential=credential,
        )
```

The important property is that:

``` text
credential_for(...)
```

returns a credential derived from the **current invocation**, not from a
persistent gateway-side user credential store.

## Security Requirements

### SR-1: No persistent downstream bearer credentials

The gateway MUST NOT persist downstream access or refresh tokens.

### SR-2: No token logging

Authorization headers and bearer tokens MUST be redacted before
application logging, OpenTelemetry export, exception reporting, HTTP
tracing, or audit-event serialization.

### SR-3: Issuer isolation

Credentials MUST be associated with the expected authorization server. A
credential associated with Provider A MUST NOT be reused for Provider B.

### SR-4: Resource/audience validation

The gateway MUST validate that the token is intended for the resource
accepting it.

### SR-5: Scope validation

Each protected tool MUST declare the minimum scopes it requires.

### SR-6: Explicit downstream forwarding policy

A credential MUST NOT be forwarded merely because the gateway accepted
it. Forwarding requires an explicit policy confirming that the
credential is valid and intended for the downstream resource.

### SR-7: Short transient lifetime

References to bearer credentials SHOULD be discarded as soon as the
downstream invocation completes.

### SR-8: No credential leakage across concurrent requests

Request-scoped authorization context MUST remain isolated between users,
sessions, tools, and concurrent invocations.

### SR-9: Trusted authorization-server configuration

The gateway MUST maintain an allowlist or equivalent trusted
configuration of authorization servers for each protected tool group.
Authorization endpoints supplied dynamically by untrusted input MUST NOT
become arbitrary redirect/authentication destinations.

## Security Properties

This architecture gives us several useful properties.

### Gateway database compromise

A database compromise does not reveal stored downstream refresh tokens
because none are stored.

### Reduced credential-custodian responsibility

The gateway does not need to implement refresh-token persistence,
rotation, revocation storage, or recovery for every downstream provider.

### Provider isolation

Credentials can be isolated according to issuer/resource instead of
sharing one gateway-wide authentication context.

### Least privilege

Tool-specific scope requirements and scope step-up allow the client to
request additional privileges only when required.

### Reduced blast radius

A transient access token could still be exposed by a compromised running
gateway, but compromise of persistent storage does not automatically
expose long-lived credentials for every connected provider.

This architecture therefore **reduces** credential exposure; it does not
make the gateway unable to observe credentials.

## Threat Model Limitation

The gateway is still in the request path.

Therefore:

``` text
Client
   |
   | bearer token
   v
Gateway
```

means a compromised gateway process can potentially observe or misuse
the current access token.

This ADR protects primarily against:

-   persistent credential theft,
-   database exfiltration of refresh tokens,
-   accidental long-term token retention,
-   unnecessary credential custody.

It does **not** protect against a fully compromised gateway using
credentials that are currently passing through it.

Sender-constrained tokens, DPoP, mTLS, narrowly scoped tokens, short
token lifetimes, or architectures where the gateway never receives the
downstream credential may further reduce this risk where supported.

## Compatibility Gate

Before this ADR moves from **Proposed** to **Accepted**, we must test
the MCP hosts we intend to support.

At minimum, verify:

``` text
[ ] Client connects to one MCP endpoint.

[ ] Public/tool-discovery behavior works as intended.

[ ] Calling Tool A can initiate OAuth A.

[ ] OAuth A credentials remain usable for later Tool A calls.

[ ] Calling Tool B can independently initiate OAuth B.

[ ] OAuth B does not overwrite or contaminate OAuth A credentials.

[ ] Returning to Tool A uses/refreshed OAuth A credentials.

[ ] A token from A is never presented as authorization for B.

[ ] Scope step-up works for a higher-privilege tool.

[ ] Logout/revocation behavior is understood.

[ ] FastMCP middleware can expose the required per-tool/resource
    authorization challenge behavior.

[ ] Downstream token forwarding satisfies OAuth resource/audience
    requirements.
```

Candidate hosts should include the actual clients we intend to support
rather than relying solely on SDK-level tests.

## Implementation Guidance

Separate four concepts in code:

``` text
Tool
 |
 +--> ToolAuthPolicy
 |      |
 |      +--> authorization server
 |      +--> protected resource
 |      +--> required scopes
 |      +--> token validator
 |
 +--> DownstreamRoute
        |
        +--> endpoint
        +--> credential forwarding policy
```

Avoid combining them into a single generic "OAuth provider" abstraction.

Authentication answers:

> Who issued this credential and for which protected resource?

Authorization answers:

> May this identity invoke this tool?

Delegation/forwarding answers:

> May this credential be presented to the downstream resource?

These are related but distinct decisions.

## Observability

Authorization decisions should be observable without exposing
credentials.

Safe audit information can include:

``` text
request_id
user/subject identifier where appropriate
tool name
authorization policy ID
issuer
validated scopes
authorization result
downstream route
```

Do not record:

``` text
Authorization header
access token
refresh token
authorization code
client secret
PKCE verifier
```

Telemetry libraries and HTTP client/server instrumentation must be
configured to redact authorization headers.

## Open Questions

1.  Which target MCP clients correctly support multiple
    authorization-server contexts behind one MCP endpoint?
2.  How should separate Protected Resource Metadata documents be
    addressed for different tool/provider policies?
3.  Does FastMCP provide sufficient hooks for dynamic per-tool
    challenges, or should an authorization middleware sit in front of
    FastMCP?
4.  For each downstream MCP, is the client-obtained token actually valid
    for that downstream resource, or is OAuth token exchange/delegation
    required?
5.  How should a client discover authorization requirements before the
    first tool invocation, if desired?
6.  What UX do target hosts provide when authorization is triggered
    halfway through an agent workflow?
7.  How are revoked downstream authorizations surfaced back to the
    client?

## Decision Validation

A proof of concept should contain two downstream protected tool groups
using **different authorization servers**:

``` text
Single endpoint:

https://gateway.example.com/mcp

Tools:

provider_a_whoami
provider_b_whoami
```

The test succeeds when a compatible MCP client can:

1.  Connect to the single endpoint.
2.  Invoke `provider_a_whoami` and authorize with Provider A.
3.  Invoke `provider_b_whoami` and independently authorize with Provider
    B.
4.  Invoke `provider_a_whoami` again without losing Provider A's
    authorization.
5.  Restart the gateway without losing either authorization.
6.  Confirm that no Provider A/B access or refresh token exists in
    gateway persistent storage.
7.  Confirm through instrumentation tests that tokens are absent from
    logs and traces.

This proof of concept should be completed before relying on the
architecture for production interoperability.

## References

-   Model Context Protocol Apps documentation, **Authorization** ---
    describes per-server and per-tool authorization, Protected Resource
    Metadata, HTTP `401` challenges, and client retry behavior.
-   MCP TypeScript SDK v2 migration documentation --- describes
    issuer-bound credentials (SEP-2352), multi-authorization-server
    credential storage, and scope step-up behavior.
-   MCP Python SDK v2 migration documentation --- describes binding
    OAuth client credentials to the authorization server that issued
    them.
-   RFC 9728 --- OAuth 2.0 Protected Resource Metadata.
-   RFC 8707 --- Resource Indicators for OAuth 2.0.
-   MCP Authorization specification applicable to the protocol version
    negotiated by the target client.
