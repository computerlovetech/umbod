import { render } from 'svelte/server';
import { describe, expect, test, vi } from 'vitest';
import type { ToastApi } from '$lib/components/feedback/toast-state.svelte';
import type { DashboardApi } from '$lib/dashboard/api';
import { InMemoryDashboardApi } from '$lib/dashboard/infrastructure/in-memory-api';
import { catalogue, personalConnector, sharedConnector } from '$lib/dashboard/test-fixtures';
import type { PersonalConnectionsApi } from '$lib/personal-connections/api';
import { InMemoryPersonalConnectionsApi } from '$lib/personal-connections/infrastructure/in-memory-api';
import ConnectorCard from './ConnectorCard.svelte';
import Dashboard from './Dashboard.svelte';

vi.mock('$lib/components/feedback', () => ({
  useToast: (): ToastApi => ({
    success: (): number => 1, warning: (): number => 1, error: (): number => 1, dismiss: (): void => {}
  })
}));

describe('dashboard presentation', () => {
  test('hides privileged navigation until the independent current-user read completes', (): void => {
    const currentUser = vi.fn();
    const body = render(Dashboard, { props: {
      mcpEndpoint: 'https://umbod.test/mcp',
      createCurrentUserApi: () => ({ currentUser }),
      createApi: (): DashboardApi => new InMemoryDashboardApi(catalogue),
      createPersonalApi: (): PersonalConnectionsApi => new InMemoryPersonalConnectionsApi([])
    } }).body;
    expect(body).toContain('aria-label="Workspace sidebar"');
    expect(body).toContain('aria-label="Workspace navigation"');
    expect(body).toContain('Your account');
    expect(currentUser).not.toHaveBeenCalled();
    expect(body).toContain('href="/dashboard"');
    expect(body).toContain('aria-busy="true"');
    for (const path of ['/admin', '/admin/connectors', '/admin/group-permissions', '/admin/mcp-setup', '/admin/instance-configuration']) {
      expect(body.includes(`href="${path}"`)).toBe(false);
    }
  });

  test('initial render is passive, concise and contains shared shell and client setup', (): void => {
    const api: DashboardApi = new InMemoryDashboardApi(catalogue);
    const personal: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([]);
    const list = vi.spyOn(api.catalogue, 'list');
    const personalList = vi.spyOn(personal.connections, 'list');
    const body = render(Dashboard, { props: {
      mcpEndpoint: 'https://umbod.test/mcp',
      createApi: (): DashboardApi => api,
      createPersonalApi: (): PersonalConnectionsApi => personal
    } }).body;
    expect(body).toContain('Dashboard</h1>');
    expect(body).toContain('aria-busy="true"');
    expect(body).not.toContain('Loading connectors');
    expect(body).toContain('MCP setup');
    expect(body).toContain('https://umbod.test/mcp');
    expect(body).not.toContain('/admin');
    expect(body).not.toContain('Connections');
    expect(body).not.toContain('Manage group permissions');
    expect((body.match(/<h1/g) ?? []).length).toBe(1);
    expect(list).not.toHaveBeenCalled();
    expect(personalList).not.toHaveBeenCalled();
  });

  test.each([
    { ...sharedConnector, kind: 'native' as const, label: 'Native' },
    { ...sharedConnector, kind: 'openapi' as const, label: 'OpenAPI' },
    { ...sharedConnector, label: 'MCP server' },
    { ...personalConnector, label: 'MCP server' }
  ])('consistent entries preserve $kind terminology and show read-only capabilities', ({ label, ...connector }): void => {
    const body = render(ConnectorCard, { props: { connector } }).body;
    expect(body).toContain(connector.display_name);
    expect(body).toContain(label);
    expect(body).toContain('Show details');
    expect(body).not.toMatch(/<details[^>]*\sopen/);
    expect(body).not.toContain('Personal access');
    expect(body).not.toContain('<button');
    expect(body).not.toContain('Configure');
    if (connector.kind !== 'downstream_mcp') expect(body).not.toContain('MCP server');
  });
});
