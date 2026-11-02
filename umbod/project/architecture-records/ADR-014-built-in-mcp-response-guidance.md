# ADR-014: Built-In MCP Responses With Explicit Agent Guidance

- **Status:** Accepted
- **Date:** 2026-11-02
- **Scope:** Built-in filesystem and administrator MCP tools; connector-tool adoption is deferred
- **Implementation status:** Initial `schema_version: 1` contract implemented with shared guidance, rendering, and separate extension boundaries; see [application diagnostics](../../docs/operations/application-diagnostics.md).

## Decision

Construct typed outcomes in the transport-neutral [responses core module](../../api/src/umbod/core/responses/README.md); present them through the [MCP adapter](../../api/src/umbod/mcp/responses/README.md). Separate domain payloads, agent guidance, and client metadata. This covers all 13 filesystem and both administrator tools, including connector configuration, and is mandatory for every built-in MCP tool created going forward. Connector-provided tools remain excluded pending a separate adoption decision.

- **Success:** retain the existing payload in `structuredContent`, conforming to its advertised `outputSchema`. Retain model-readable `content`; follow MCP's recommendation to also provide serialized structured output in text for compatibility.
- **Tool failure:** set `isError: true` and provide concise text explaining the failure and corrective action. Never fabricate a successful payload. Protocol errors remain JSON-RPC errors; input-required responses are neither success nor failure.
- **Agent guidance:** explicitly model outcome, operation state, safe error code/message, field issues, retry advice, corrective instructions, notices, and approved agent-visible extensions. Render essential guidance into `content`; an agent must not need `_meta` to avoid an unsafe retry.
- **Client metadata:** use namespaced `_meta["computerlove.tech/umbod"]` for schema version, server version/revision, request correlation, the same guidance in structured form, and client-facing extensions. Include a useful request reference in failure content. Clients need explicit integration to interpret Umbod's custom fields.
- **Extensions:** distinguish guidance extensions from client-metadata extensions. Each needs a namespaced key and a defined, versioned DTO/schema. Agent extensions also require an approved renderer; never dump unknown extensions into model context. Adding client metadata must not implicitly change agent-visible content. Sanitize both surfaces; `_meta` is not a universal confidentiality boundary.

Outcome and execution state are different facts. A failed response can follow a completed operation. Use explicit admission/completion evidence, not `isError` or logging events, to select `not_started`, `completed`, or `unknown`. Completed or unknown failures permit only `inspect_before_retry` or `never`. Retry advice neither grants permission nor establishes idempotency.

## Context and rationale

MCP defines structured output, text content, tool errors, and extensible metadata, but does not require hosts to expose custom `_meta` fields to models. The ChatGPT Apps SDK explicitly keeps tool-result `_meta` out of model context. Metadata-only recovery instructions therefore cannot protect agents across clients.

Umbod uses immutable DTOs, safe diagnostics, progress markers, and built-in opt-in. Shared guidance and rendering extend this foundation as one response system. This supplements, without superseding, ADR-004, ADR-008, and ADR-013.

## Creating built-in responses

1. Compose [ToolResponseMetadataFactory](../../api/src/umbod/core/responses/factory.py) with server identity and scoped request correlation. Use its success/failure methods and [immutable DTOs](../../api/src/umbod/core/responses/models.py), including bounded `ToolErrorDetails` and `ToolArgumentIssue`. Supply approved diagnostics, not raw exceptions or submitted values.
2. Register every built-in, including new tools, through [observed registration](../../api/src/umbod/mcp/tools/registration.py) with `builtin_response=True`. Keep payload creation in the tool; central adaptation owns metadata and guidance rendering. New built-ins must not bypass the shared response contract, rendering, or retry-safety rules. Preserve unrelated metadata and existing input/success schemas.
3. Mark business admission and successful primary completion using [invocation-local progress](../../api/src/umbod/mcp/responses/progress.py). Mark completion before enrichment or rendering can fail. Use `unknown` where durable effects cannot be proved, including administrator rejection after a potentially committed write/read-back sequence.
4. Use the core guidance DTO; derive text and structured guidance from that object. Protocol objects/rendering belong in the MCP adapter. Response construction must not depend on optional signal receivers.
5. Use `schema_version: 1` for the initial nested contract. Increment it for incompatible changes after publication, not for revisions of an unreleased draft. No earlier response layout is supported.

### Confirmation and elicitation

Follow [filesystem_delete_file](../../api/src/umbod/mcp/filesystem/deletion.py) and its [approval adapter](../../api/src/umbod/mcp/filesystem/approval.py):

1. Validate arguments, current eligibility, and expected revision before requesting confirmation. Describe the authorized target and irreversible effects; escape untrusted names. Deletion removes the namespace entry, ownership, and grants, not stored bytes; it has no trash or restore.
2. Follow the negotiated branch. Modern calls return `InputRequiredToolResult` containing `InputRequiredResult`: a `filesystem_delete_approval` elicitation request requiring boolean `value`, plus opaque `requestState`. Legacy calls use `Context.elicit` with strict `FileDeletionConfirmation`. Unsupported approval fails closed; the current adapter rejects approval through `execute_code`.
3. Return input-required results unchanged through observation, response adaptation, and middleware. Do not wrap them as ordinary tool content, attach a terminal success/failure classification, or mutate while awaiting approval. Clients echo continuation state unchanged; never ask the model to manufacture approval or parse that state.
4. Accept only explicit acceptance with boolean `true`. The [approval state](../../api/src/umbod/mcp/filesystem/approval_state.py) binds caller, client, command, a five-minute expiry, and a single-use nonce; the framework seals continuation state at the wire boundary. Verify bindings and consume the nonce, recapture the caller, and recheck current authorization and revision in the deletion service. Decline, cancellation, invalid/expired/replayed state, or unavailable elicitation must never authorize deletion.
5. Only after deletion returns, mark completion and construct `FileDeletionResult` with success text. Preserve native protocol errors and cancellations where applicable; render terminal tool failures through the common failure path. Approval is not permission and does not make deletion idempotent.

## Alternatives considered

- **Recovery only in `_meta`:** compact and machine-readable, but hosts can omit it from model context; rejected as the sole guidance surface.
- **Wrap or add common fields to domain payloads:** readily discoverable through output schemas, but changes existing tool contracts; rejected for this adoption.
- **Independent per-tool strings and metadata:** preserves local flexibility, but duplicates policy and permits contradictory advice; replaced by shared typed guidance and explicit rendering.

## Consequences

Payload compatibility is preserved, while agent-critical instructions remain available without custom client support. Text duplicates some structured information and consumes context; deriving both views from one DTO is an ongoing obligation. Keep missing and inaccessible nodes indistinguishable and exclude credentials, hidden destinations, arbitrary keys, and raw exceptions.

Test schema preservation, text/metadata agreement without `_meta` visibility, extension visibility, post-mutation failures, connector non-adoption, and approval without premature mutation/success. Extend the [response tests](../../api/tests/umbod/mcp/responses/) and [approval tests](../../api/tests/umbod/mcp/filesystem/test_deletion_approval.py); these verify the shared contract and rendering.

## Confidence and reevaluation

Protocol mechanisms and current implementation boundaries are documented; a cross-client compatibility matrix has not been established. Reevaluate through a new ADR if connector adoption, host behavior, metadata evolution, or confirmation requirements cannot preserve these boundaries.

## Supporting material

- [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) — Structured output, model-visible tool errors, and output-schema rules.
- [MCP metadata](https://modelcontextprotocol.io/specification/2025-11-25/basic#meta) — Namespaced protocol extension fields.
- [ChatGPT Apps SDK reference](https://developers.openai.com/apps-sdk/reference) — Tool-result metadata is hidden from the model in that host.
- [ADR-004](ADR-004-single-backend-api-and-desktop-boundary.md), [ADR-008](ADR-008-event-synchronized-tool-runtime.md), and [ADR-013](ADR-013-signal-owned-application-logging.md) — Shared semantics, explicit composition, and signal-owned observation.
