import { z } from 'zod';

export const connectorKindSchema = z.enum(['catalog', 'openapi', 'mcp']);
export type ConnectorKind = z.infer<typeof connectorKindSchema>;
export type Available<T> = { status: 'available'; value: T } | { status: 'unavailable' };

export function availableSchema<T>(value: z.ZodType<T>): z.ZodType<Available<T>> {
  return z.discriminatedUnion('status', [
    z.strictObject({ status: z.literal('available'), value }),
    z.strictObject({ status: z.literal('unavailable') })
  ]);
}

const countSchema = z.number().int().nonnegative();
export const toolCountsSchema = z.object({ enabled: countSchema, known: countSchema });
export type ToolCounts = z.infer<typeof toolCountsSchema>;
export const attentionCountsSchema = z.object({
  unconfigured: countSchema,
  draft: countSchema,
  unpublished: countSchema,
  unhealthy: countSchema
});
export const connectorCountsSchema = attentionCountsSchema.extend({
  configured: countSchema,
  published: countSchema
});
export type ConnectorCounts = z.infer<typeof connectorCountsSchema>;
export const overviewBreakdownSchema = z.object({
  kind: connectorKindSchema,
  connectors: availableSchema(connectorCountsSchema),
  tools: availableSchema(toolCountsSchema)
});
export type OverviewBreakdown = z.infer<typeof overviewBreakdownSchema>;
export const adminOverviewResponseSchema = z.object({
  breakdown: overviewBreakdownSchema.array().length(3).refine(
    (entries) => entries.every((entry, index) => entry.kind === connectorKindSchema.options[index]),
    { message: 'Expected catalog, openapi, mcp breakdown order' }
  ),
  configured: availableSchema(countSchema),
  published: availableSchema(countSchema),
  tools: availableSchema(toolCountsSchema),
  permission_groups: availableSchema(countSchema),
  attention: availableSchema(attentionCountsSchema)
});
export type AdminOverviewResponse = z.infer<typeof adminOverviewResponseSchema>;
export const adminOverviewSchema = adminOverviewResponseSchema.omit({ permission_groups: true }).extend({
  permissionGroups: availableSchema(countSchema)
});
export type AdminOverview = z.infer<typeof adminOverviewSchema>;

export function available<T>(value: T): Available<T> {
  return { status: 'available', value };
}

export function unavailableOverview(): AdminOverview {
  return {
    breakdown: connectorKindSchema.options.map((kind) => ({
      kind, connectors: { status: 'unavailable' }, tools: { status: 'unavailable' }
    })),
    configured: { status: 'unavailable' },
    published: { status: 'unavailable' },
    tools: { status: 'unavailable' },
    permissionGroups: { status: 'unavailable' },
    attention: { status: 'unavailable' }
  };
}
