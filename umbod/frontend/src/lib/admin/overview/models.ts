import { z } from 'zod';

export const connectorKindSchema = z.enum(['catalog', 'openapi', 'mcp']);
export type ConnectorKind = z.infer<typeof connectorKindSchema>;
export const overviewConnectorSchema = z.object({
  id: z.string(),
  publicationStatus: z.enum(['unconfigured', 'draft', 'published', 'unpublished']),
  discoveryStatus: z.enum(['unknown', 'healthy', 'unhealthy'])
});
export type OverviewConnector = z.infer<typeof overviewConnectorSchema>;
export const overviewToolSchema = z.object({ activationStatus: z.enum(['enabled', 'disabled']) });
export type OverviewTool = z.infer<typeof overviewToolSchema>;
export type Available<T> = { status: 'available'; value: T } | { status: 'unavailable' };
export type ToolCounts = { enabled: number; known: number };
export type ConnectorCounts = {
  configured: number;
  published: number;
  unconfigured: number;
  draft: number;
  unpublished: number;
  unhealthy: number;
};
export type OverviewBreakdown = {
  kind: ConnectorKind;
  connectors: Available<ConnectorCounts>;
  tools: Available<ToolCounts>;
};
export type AdminOverview = {
  breakdown: OverviewBreakdown[];
  configured: Available<number>;
  published: Available<number>;
  tools: Available<ToolCounts>;
  permissionGroups: Available<number>;
  attention: Available<Pick<ConnectorCounts, 'unconfigured' | 'draft' | 'unpublished' | 'unhealthy'>>;
};

export function available<T>(value: T): Available<T> {
  return { status: 'available', value };
}
