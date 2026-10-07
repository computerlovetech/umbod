import { describe, expect, test } from 'vitest';
import { loadAdminOverview } from './aggregate';
import { InMemoryOverviewSource, type InMemoryOverviewData } from './in-memory-source';
import { available, overviewToolSchema, type AdminOverview, type ConnectorKind, type OverviewConnector } from './models';
import type { OverviewSource } from './port';

function emptyOverviewData(): InMemoryOverviewData {
  return { connectors: { catalog: available([]), openapi: available([]), mcp: available([]) }, tools: { catalog: {}, openapi: {}, mcp: {} }, permissionGroups: available(0) };
}

function connector(id: string, publicationStatus: OverviewConnector['publicationStatus'], discoveryStatus: OverviewConnector['discoveryStatus'] = 'unknown'): OverviewConnector {
  return { id, publicationStatus, discoveryStatus };
}

function mixedData(): InMemoryOverviewData {
  const data = emptyOverviewData();
  data.connectors.catalog = available([connector('same', 'published'), connector('draft', 'draft'), connector('setup', 'unconfigured')]);
  data.connectors.openapi = available([connector('same', 'unpublished')]);
  data.connectors.mcp = available([connector('same', 'published', 'unhealthy'), connector('unknown', 'unpublished')]);
  for (const kind of ['catalog', 'openapi', 'mcp'] as ConnectorKind[]) {
    const result = data.connectors[kind];
    if (result.status === 'available') {
      for (const entry of result.value) {
        data.tools[kind][entry.id] = available([
          overviewToolSchema.parse({ tool_id: 'duplicate', activationStatus: 'enabled' }),
          overviewToolSchema.parse({ tool_id: 'disabled', activationStatus: 'disabled' })
        ]);
      }
    }
  }
  data.permissionGroups = available(3);
  return data;
}

async function overview(data: InMemoryOverviewData): Promise<AdminOverview> {
  const source: OverviewSource = new InMemoryOverviewSource(data);
  return loadAdminOverview(source);
}

describe('overview aggregation through its source port', () => {
  test('counts every connector, including connector-scoped duplicate tool IDs and unknown MCP discovery', async () => {
    const result = await overview(mixedData());
    expect(result.configured).toEqual(available(5));
    expect(result.published).toEqual(available(2));
    expect(result.tools).toEqual(available({ enabled: 6, known: 12 }));
    expect(result.permissionGroups).toEqual(available(3));
    expect(result.attention).toEqual(available({ unconfigured: 1, draft: 1, unpublished: 2, unhealthy: 1 }));
    expect(result.breakdown.map((row) => row.tools)).toEqual([available({ enabled: 3, known: 6 }), available({ enabled: 1, known: 2 }), available({ enabled: 2, known: 4 })]);
  });

  test('successful empty sources produce genuine zero counts', async () => {
    const result = await overview(emptyOverviewData());
    expect(result.configured).toEqual(available(0));
    expect(result.published).toEqual(available(0));
    expect(result.tools).toEqual(available({ enabled: 0, known: 0 }));
    expect(result.permissionGroups).toEqual(available(0));
    expect(result.attention).toEqual(available({ unconfigured: 0, draft: 0, unpublished: 0, unhealthy: 0 }));
  });

  test.each(['catalog', 'openapi', 'mcp'] as ConnectorKind[])('preserves independent counts when %s listing is unavailable', async (kind) => {
    const data = mixedData();
    data.connectors[kind] = { status: 'unavailable' };
    const result = await overview(data);
    expect(result.configured.status).toBe('unavailable');
    expect(result.published.status).toBe('unavailable');
    expect(result.tools.status).toBe('unavailable');
    expect(result.attention.status).toBe('unavailable');
    expect(result.breakdown.filter((row) => row.kind !== kind).every((row) => row.connectors.status === 'available' && row.tools.status === 'available')).toBe(true);
    expect(result.permissionGroups).toEqual(available(3));
  });

  test.each(['catalog', 'openapi', 'mcp'] as ConnectorKind[])('preserves connector counts but invalidates %s tool subtotal after one tool failure', async (kind) => {
    const data = mixedData();
    data.tools[kind].same = { status: 'unavailable' };
    const result = await overview(data);
    expect(result.tools.status).toBe('unavailable');
    expect(result.breakdown.find((row) => row.kind === kind)?.tools.status).toBe('unavailable');
    expect(result.configured).toEqual(available(5));
    expect(result.published).toEqual(available(2));
    expect(result.attention.status).toBe('available');
    expect(result.breakdown.filter((row) => row.kind !== kind).every((row) => row.tools.status === 'available')).toBe(true);
  });

  test('permission group failure does not invalidate connector data', async () => {
    const data = mixedData();
    data.permissionGroups = { status: 'unavailable' };
    const result = await overview(data);
    expect(result.permissionGroups.status).toBe('unavailable');
    expect(result.configured).toEqual(available(5));
  });

  test('bounds tool concurrency globally across connector families', async () => {
    const data = emptyOverviewData();
    for (const kind of ['catalog', 'openapi', 'mcp'] as ConnectorKind[]) {
      const connectors = Array.from({ length: 10 }, (_, index) => connector(String(index), 'published'));
      data.connectors[kind] = available(connectors);
      for (const entry of connectors) data.tools[kind][entry.id] = available([]);
    }
    const memory: OverviewSource = new InMemoryOverviewSource(data);
    let active = 0;
    let peak = 0;
    let calls = 0;
    const source: OverviewSource = {
      listConnectors: (kind) => memory.listConnectors(kind),
      countPermissionGroups: () => memory.countPermissionGroups(),
      async listTools(kind, id) {
        active++;
        calls++;
        peak = Math.max(peak, active);
        await new Promise<void>((resolve) => setTimeout(resolve, 1));
        active--;
        return memory.listTools(kind, id);
      }
    };
    await loadAdminOverview(source);
    expect(calls).toBe(30);
    expect(peak).toBe(6);
  });
});
