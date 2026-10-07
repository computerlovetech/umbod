import { render } from 'svelte/server';
import { describe, expect, test } from 'vitest';
import { loadAdminOverview } from '$lib/admin/overview/aggregate';
import { InMemoryOverviewSource } from '$lib/admin/overview/in-memory-source';
import { available, type AdminOverview } from '$lib/admin/overview/models';
import AdminOverviewDashboard from './AdminOverviewDashboard.svelte';

async function emptyOverview(): Promise<AdminOverview> {
  return loadAdminOverview(new InMemoryOverviewSource({ connectors: { catalog: available([]), openapi: available([]), mcp: available([]) }, tools: { catalog: {}, openapi: {}, mcp: {} }, permissionGroups: available(0) }));
}

describe('admin overview dashboard SSR', () => {
  test('renders four primary cards and linked family breakdown with genuine zero counts', async () => {
    const body = render(AdminOverviewDashboard, { props: { overview: await emptyOverview() } }).body;
    expect(body).toContain('Configured connectors');
    expect(body).toContain('Enabled / known tools');
    expect(body).toContain('Published connectors');
    expect(body).toContain('Registered permission groups');
    expect(body).toContain('including saved MCP proxies');
    expect(body).toContain('0 / 0');
    expect(body).toContain('href="/admin/openapi-connectors"');
    expect(body).toContain('href="/admin/downstream-mcp-connectors"');
    expect(body).toContain('scope="col"');
    expect(body).toContain('scope="row"');
    expect(body).toContain('tabindex="0"');
    expect(body).not.toContain('Needs attention');
    expect(body).not.toContain('Unavailable');
  });

  test('renders only positive attention counts without claiming overall health', async () => {
    const overview = await emptyOverview();
    overview.attention = available({ unconfigured: 2, draft: 1, unpublished: 0, unhealthy: 1 });
    const body = render(AdminOverviewDashboard, { props: { overview } }).body;
    expect(body).toContain('Needs attention');
    expect(body).toContain('Unconfigured connectors');
    expect(body).toContain('Draft connectors');
    expect(body).toContain('Unhealthy MCP discovery');
    expect(body).not.toContain('Unpublished connectors');
    expect(body).toContain('not service errors');
    expect(body).toContain('Unknown MCP discovery is not counted as unhealthy');
    expect(body).not.toContain('System health');
  });

  test('partial data renders unavailable counts and an explicit unknown attention warning', async () => {
    const overview = await emptyOverview();
    overview.configured = { status: 'unavailable' };
    overview.tools = { status: 'unavailable' };
    overview.attention = { status: 'unavailable' };
    overview.breakdown[0].connectors = { status: 'unavailable' };
    overview.breakdown[0].tools = { status: 'unavailable' };
    const body = render(AdminOverviewDashboard, { props: { overview } }).body;
    expect(body).toContain('Unavailable');
    expect(body).toContain('Unavailable counts are not zero');
    expect(body).toContain('Connector attention counts are unavailable');
    expect(body).toContain('could not be fully assessed');
    expect(body).toContain('0 / 0');
  });
});
