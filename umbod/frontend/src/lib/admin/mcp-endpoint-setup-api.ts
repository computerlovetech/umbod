import { SchemaValidationError, type Transport } from './infrastructure/transport';
import {
  mcpEndpointAccessRequestSchema,
  mcpEndpointAccessResultSchema,
  mcpRegistryPageSchema,
  mcpRegistrySearchSchema,
  type McpEndpointAccessRequest,
  type McpEndpointAccessResult,
  type McpEndpointSetup,
  type McpRegistryPage,
  type McpRegistrySearch
} from './mcp-endpoint-setup';

export class McpEndpointSetupRoute implements McpEndpointSetup {
  constructor(private readonly transport: Transport) {}

  async search(query: McpRegistrySearch): Promise<McpRegistryPage> {
    const parsed = mcpRegistrySearchSchema.safeParse(query);
    if (!parsed.success) throw new SchemaValidationError('outbound', parsed.error.issues);
    const { term, limit, cursor } = parsed.data;
    const params = new URLSearchParams({ term });
    if (limit !== undefined) params.set('limit', String(limit));
    if (cursor !== undefined) params.set('cursor', cursor);
    return this.transport.request({
      method: 'GET',
      path: `/admin/connectors/mcp/registry/search?${params}`,
      outputSchema: mcpRegistryPageSchema
    });
  }

  checkAccess(endpointUrl: McpEndpointAccessRequest['endpoint_url']): Promise<McpEndpointAccessResult> {
    return this.transport.request({
      method: 'POST',
      path: '/admin/connectors/mcp/check-access',
      body: { endpoint_url: endpointUrl },
      inputSchema: mcpEndpointAccessRequestSchema,
      outputSchema: mcpEndpointAccessResultSchema.refine((result): boolean =>
        result.oauth.kind !== 'oauth_discovered' || result.oauth.metadata.endpoint_url === endpointUrl
      )
    });
  }
}
