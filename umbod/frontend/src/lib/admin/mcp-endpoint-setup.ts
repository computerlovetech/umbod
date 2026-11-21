import { z } from 'zod';
import { discoveryEndpointSchema, endpointDiscoveryResultSchema } from './personal-mcp-servers/domain/discovery';

const cursorSchema = z.string().refine((cursor): boolean => [...cursor].length <= 2048);
const nonBlankTextSchema = z.string().trim().min(1);

export const mcpRegistrySearchSchema = z.strictObject({
  term: z.string().trim().refine((term): boolean => {
    const length = [...term].length;
    return length >= 3 && length <= 256;
  }),
  limit: z.number().int().min(1).max(100).optional(),
  cursor: cursorSchema.optional()
});

export const mcpRegistryServerSchema = z.strictObject({
  name: nonBlankTextSchema,
  title: nonBlankTextSchema,
  description: z.string(),
  version: nonBlankTextSchema,
  endpoints: z.array(z.strictObject({
    url: discoveryEndpointSchema.refine((url): boolean => !/[{}]/.test(url)),
    required_headers: z.array(nonBlankTextSchema)
  })).min(1)
});

export const mcpRegistryPageSchema = z.strictObject({
  servers: z.array(mcpRegistryServerSchema),
  next_cursor: cursorSchema
});

export const mcpEndpointAccessRequestSchema = z.strictObject({ endpoint_url: discoveryEndpointSchema });

export const mcpEndpointAccessResultSchema = z.strictObject({
  anonymous_initialization: z.discriminatedUnion('kind', [
    z.strictObject({ kind: z.literal('anonymous_initialization_succeeded') }),
    z.strictObject({ kind: z.literal('anonymous_access_rejected'), status_code: z.literal([401, 403]) }),
    z.strictObject({
      kind: z.literal('inconclusive'),
      reason: z.enum(['endpoint_not_found', 'unreachable', 'timeout', 'invalid_mcp_protocol', 'unsafe_destination', 'redirected', 'response_too_large'])
    })
  ]),
  oauth: z.discriminatedUnion('kind', [
    z.strictObject({ kind: z.literal('oauth_discovered'), metadata: endpointDiscoveryResultSchema }),
    z.strictObject({ kind: z.literal('oauth_not_confirmed') }),
    z.strictObject({ kind: z.literal('oauth_not_checked') })
  ])
});

export type McpRegistrySearch = z.infer<typeof mcpRegistrySearchSchema>;
export type McpRegistryPage = z.infer<typeof mcpRegistryPageSchema>;
export type McpRegistryServer = z.infer<typeof mcpRegistryServerSchema>;
export type McpEndpointAccessRequest = z.infer<typeof mcpEndpointAccessRequestSchema>;
export type McpEndpointAccessResult = z.infer<typeof mcpEndpointAccessResultSchema>;

export interface McpEndpointSetup {
  search(query: McpRegistrySearch): Promise<McpRegistryPage>;
  checkAccess(endpointUrl: McpEndpointAccessRequest['endpoint_url']): Promise<McpEndpointAccessResult>;
}
