# Application diagnostics

## Investigating a failure

1. Find the server-generated `X-Request-ID` and match it to the invocation completion record. `X-Umbod-Version` and `X-Umbod-Revision` identify the serving build. Match related records by trace, connector, tool, and operation; audit and invocation records can describe the same failure.
2. Check `mcp.failure.category`, `mcp.failure.origin`, `mcp.failure.stage`, and `mcp.failure.reason`. If `mcp.downstream.response_received` is true, `mcp.downstream.http.status_code` describes the downstream exchange, not Umbod’s public response. Absent response evidence does not prove that Umbod never contacted the service.
3. Use sanitized exception types and frames for unexpected failures. Validation, authorization, and known rejections normally log at WARNING; unexpected runtime, storage, and contract failures remain ERROR. Do not replay a write just because its response failed.

For personal connector OAuth, correlate the request ID and `connector.id_hash`, then check `oauth.stage`, `oauth.reason`, and response evidence. An expired personal MCP authorization is different from an expired runtime target: renew the connection when Umbod reports `authorization_expired`.

## Privacy rules

Keep credentials, OAuth callback queries, request and response bodies, tool arguments and results, personal data, and signed URLs out of application logs. Apply the same protections to gateways, collectors, and error reporters. Debug logging does not relax these rules. [OTLP exports](telemetry-ingestion.md) are separate: accepted payloads can contain client-supplied sensitive data and need their own access and retention controls.

## Conversation-visible response diagnostics

[Built-in filesystem, administrator, and agent diagnostics tools](../reference/built-in-tools.md) put essential recovery advice in the result text. Clients can also read structured guidance in `_meta["computerlove.tech/umbod"]` (`schema_version: 1`), which includes request and build identity. Connector tools do not share this guidance contract.

A failure can report `not_started`, `unknown`, or `completed`. Do not automatically repeat a write with an unknown or completed outcome. Follow the returned instructions: upload completion supports retry with the same session ID, and an uncertain `report_diagnostic` submission supports retry only with identical data and the same key within its 60-day deduplication window. Neither a storage failure nor a failed receipt render acknowledges the report. An input-required result is not a terminal failure or success.
