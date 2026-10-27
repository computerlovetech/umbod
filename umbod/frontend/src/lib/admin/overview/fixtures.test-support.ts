import { available, connectorKindSchema, type AdminOverview, type AdminOverviewResponse } from './models';

export function overviewFixture(count: number = 0): AdminOverview {
  return {
    breakdown: connectorKindSchema.options.map((kind) => ({
      kind,
      connectors: available({ configured: count, published: count, unconfigured: count, draft: count, unpublished: count, unhealthy: count }),
      tools: available({ enabled: count, known: count })
    })),
    configured: available(count),
    published: available(count),
    tools: available({ enabled: count, known: count }),
    permissionGroups: available(count),
    attention: available({ unconfigured: count, draft: count, unpublished: count, unhealthy: count })
  };
}

export function overviewResponseFixture(count: number = 0): AdminOverviewResponse {
  const { permissionGroups, ...overview } = overviewFixture(count);
  return { ...overview, permission_groups: permissionGroups };
}
