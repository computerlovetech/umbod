import type { OverviewSource } from './port';
import { available, type AdminOverview, type Available, type ConnectorCounts, type ConnectorKind, type OverviewBreakdown, type OverviewConnector, type ToolCounts } from './models';

const kinds: ConnectorKind[] = ['catalog', 'openapi', 'mcp'];
const concurrency = 6;

async function boundedMap<T, R>(items: T[], operation: (item: T) => Promise<R>): Promise<R[]> {
  const results: R[] = new Array(items.length);
  let next = 0;
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, async (): Promise<void> => {
    while (next < items.length) {
      const index = next++;
      results[index] = await operation(items[index]);
    }
  }));
  return results;
}

function countConnectors(kind: ConnectorKind, connectors: OverviewConnector[]): ConnectorCounts {
  const countStatus = (status: OverviewConnector['publicationStatus']): number => connectors.filter((connector) => connector.publicationStatus === status).length;
  return {
    configured: kind === 'mcp' ? connectors.length : connectors.length - countStatus('unconfigured'),
    published: countStatus('published'),
    unconfigured: countStatus('unconfigured'),
    draft: countStatus('draft'),
    unpublished: countStatus('unpublished'),
    unhealthy: kind === 'mcp' ? connectors.filter((connector) => connector.discoveryStatus === 'unhealthy').length : 0
  };
}

function combine<T, R>(values: Available<T>[], sum: (values: T[]) => R): Available<R> {
  const collected: T[] = [];
  for (const value of values) {
    if (value.status === 'unavailable') return { status: 'unavailable' };
    collected.push(value.value);
  }
  return available(sum(collected));
}

export async function loadAdminOverview(source: OverviewSource): Promise<AdminOverview> {
  const [lists, permissionGroups] = await Promise.all([
    Promise.all(kinds.map(async (kind) => ({ kind, result: await source.listConnectors(kind) }))),
    source.countPermissionGroups()
  ]);
  const jobs = lists.flatMap(({ kind, result }) => result.status === 'available' ? result.value.map((connector) => ({ kind, id: connector.id })) : []);
  const toolResults = await boundedMap(jobs, async (job) => ({ kind: job.kind, result: await source.listTools(job.kind, job.id) }));
  const breakdown: OverviewBreakdown[] = lists.map(({ kind, result }) => ({
    kind,
    connectors: result.status === 'available' ? available(countConnectors(kind, result.value)) : { status: 'unavailable' },
    tools: result.status === 'unavailable' ? { status: 'unavailable' } : combine(toolResults.filter((entry) => entry.kind === kind).map((entry) => entry.result), (tools): ToolCounts => ({
      known: tools.reduce((count, entries) => count + entries.length, 0),
      enabled: tools.reduce((count, entries) => count + entries.filter((tool) => tool.activationStatus === 'enabled').length, 0)
    }))
  }));
  const connectorCounts = breakdown.map((entry) => entry.connectors);
  return {
    breakdown,
    permissionGroups,
    configured: combine(connectorCounts, (counts) => counts.reduce((total, count) => total + count.configured, 0)),
    published: combine(connectorCounts, (counts) => counts.reduce((total, count) => total + count.published, 0)),
    tools: combine(breakdown.map((entry) => entry.tools), (counts) => ({ enabled: counts.reduce((total, count) => total + count.enabled, 0), known: counts.reduce((total, count) => total + count.known, 0) })),
    attention: combine(connectorCounts, (counts) => ({
      unconfigured: counts.reduce((total, count) => total + count.unconfigured, 0),
      draft: counts.reduce((total, count) => total + count.draft, 0),
      unpublished: counts.reduce((total, count) => total + count.unpublished, 0),
      unhealthy: counts.reduce((total, count) => total + count.unhealthy, 0)
    }))
  };
}
