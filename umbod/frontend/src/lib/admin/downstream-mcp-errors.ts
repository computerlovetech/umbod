import { z } from 'zod';
import { HttpError, NetworkError } from './infrastructure/transport';

export const downstreamMcpErrorCodeSchema = z.enum([
  'endpoint_not_found', 'auth_rejected', 'unreachable', 'timeout', 'invalid_mcp_protocol',
  'downstream_discovery_failed', 'connector_not_found', 'connector_identity_conflict', 'public_path_conflict',
  'public_tool_name_conflict', 'downstream_connector_grants_conflict', 'credential_missing',
  'connector_unavailable', 'connector_conflict', 'tool_not_found'
]);
export const downstreamMcpErrorDetailSchema = z.object({
  code: downstreamMcpErrorCodeSchema,
  message: z.string().min(1),
  phase: z.enum(['validation', 'discovery', 'identity', 'publication', 'permission', 'credentials', 'connector']),
  retryable: z.boolean(),
  context: z.record(z.string(), z.union([z.string(), z.array(z.string())]))
}).strict();
export const downstreamMcpErrorEnvelopeSchema = z.object({ detail: downstreamMcpErrorDetailSchema }).strict();
export type DownstreamMcpErrorCode = z.infer<typeof downstreamMcpErrorCodeSchema>;
export type DownstreamMcpErrorEnvelope = z.infer<typeof downstreamMcpErrorEnvelopeSchema>;
export type DownstreamMcpActionError = { statusCode: number; data: { status: string; message: string } };

const messages: Record<DownstreamMcpErrorCode, string> = {
  endpoint_not_found: 'No MCP server was found at that endpoint. Check the URL and path.',
  auth_rejected: 'The downstream server rejected authentication. Check the authentication settings.',
  unreachable: 'The downstream MCP server could not be reached. Check the endpoint and network access.',
  timeout: 'The downstream MCP server did not respond in time. Try again or check the endpoint.',
  invalid_mcp_protocol: 'The endpoint did not respond as a valid MCP server.',
  downstream_discovery_failed: 'Discovery failed. Check the endpoint and authentication settings, then try again.',
  connector_not_found: 'This connector no longer exists. Reload the connector list.',
  connector_identity_conflict: 'A connector with that identity already exists.',
  public_path_conflict: 'That dedicated public path is already assigned to another connector.',
  public_tool_name_conflict: 'Publication conflicts with an existing public tool name.',
  downstream_connector_grants_conflict: 'Remove this connector from the affected permission groups before deleting it.',
  credential_missing: 'Configure connector credentials before trying again.',
  connector_unavailable: 'Complete successful discovery before publishing this connector.',
  connector_conflict: 'This operation conflicts with the existing connector configuration.',
  tool_not_found: 'This downstream tool no longer exists. Refresh discovery and try again.'
};

export function parseDownstreamMcpError(body: unknown): DownstreamMcpErrorEnvelope | undefined {
  const parsed = downstreamMcpErrorEnvelopeSchema.safeParse(body);
  return parsed.success ? parsed.data : undefined;
}

export function presentDownstreamMcpActionError(error: unknown, action: string): DownstreamMcpActionError {
  if (error instanceof NetworkError) return { statusCode: 503, data: { status: 'network', message: `${action} could not reach the connector service. Try again.` } };
  if (!(error instanceof HttpError)) throw error;
  const envelope = parseDownstreamMcpError(error.body);
  if (envelope) {
    const status = envelope.detail.code === 'connector_not_found' ? 'stale'
      : error.status === 409 ? 'conflict'
      : envelope.detail.code === 'auth_rejected' ? 'authentication'
      : 'invalid';
    return { statusCode: error.status, data: { status, message: messages[envelope.detail.code] } };
  }
  return { statusCode: error.status, data: { status: 'failed', message: `${action} failed. Try again.` } };
}
