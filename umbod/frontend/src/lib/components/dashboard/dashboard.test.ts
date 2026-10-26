import { render } from 'svelte/server';
import { InMemoryAttemptScheduler } from '$lib/personal-connections/infrastructure/in-memory-attempt-scheduler';
import { describe, expect, test, vi } from 'vitest';
import type { ToastApi } from '$lib/components/feedback/toast-state.svelte';
import type { DashboardApi } from '$lib/dashboard/api';
import { InMemoryDashboardApi } from '$lib/dashboard/infrastructure/in-memory-api';
import { catalogue, personalConnector, sharedConnector } from '$lib/dashboard/test-fixtures';
import type { CatalogueCapability } from '$lib/dashboard/domain/schemas';
import type { DashboardController } from '$lib/dashboard/state/port';
import { DashboardState } from '$lib/dashboard/state/dashboard-state.svelte';
import { authorizationHealth, selection } from '$lib/personal-connections/test-fixtures';
import type { PersonalConnectionsApi } from '$lib/personal-connections/api';
import { InMemoryPersonalConnectionsApi } from '$lib/personal-connections/infrastructure/in-memory-api';
import CatalogueCapabilities from './CatalogueCapabilities.svelte';
import ConnectorDetail from './ConnectorDetail.svelte';
import ConnectorWorkspace from './ConnectorWorkspace.svelte';
import Dashboard from './Dashboard.svelte';

vi.mock('$lib/components/feedback', () => ({
  useToast: (): ToastApi => ({
    success: (): number => 1, warning: (): number => 1, error: (): number => 1, dismiss: (): void => {}
  })
}));

async function loadedController(): Promise<DashboardController> {
  const state: DashboardController = new DashboardState(
    new InMemoryDashboardApi(catalogue),
    new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth }),
    undefined,
    new InMemoryAttemptScheduler()
  );
  await state.loadCatalogue();
  return state;
}

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
    for (const path of ['/admin', '/admin/connectors', '/admin/group-permissions/connectors', '/admin/group-permissions/filesystem', '/admin/filesystem', '/admin/mcp-setup', '/admin/instance-configuration']) {
      expect(body.includes(`href="${path}"`)).toBe(false);
    }
  });

  test('initial render keeps the whole main view loading without partial dashboard content', (): void => {
    const api: DashboardApi = new InMemoryDashboardApi(catalogue);
    const personal: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([]);
    const list = vi.spyOn(api.catalogue, 'list');
    const personalList = vi.spyOn(personal.connections, 'list');
    const body = render(Dashboard, { props: {
      mcpEndpoint: 'https://umbod.test/mcp',
      createApi: (): DashboardApi => api,
      createPersonalApi: (): PersonalConnectionsApi => personal
    } }).body;
    expect(body).not.toContain('Dashboard</h1>');
    expect(body).toContain('content-loading active');
    expect(body).toContain('inert');
    expect(body).toContain('aria-busy="true"');
    expect(body).not.toContain('Loading connectors');
    expect(body).not.toContain('MCP setup');
    expect(body).not.toContain('https://umbod.test/mcp');
    expect(body).not.toContain('/admin');
    expect(body).not.toContain('Connections');
    expect(body).not.toContain('Manage group permissions');
    expect((body.match(/<h1/g) ?? []).length).toBe(0);
    expect(list).not.toHaveBeenCalled();
    expect(personalList).not.toHaveBeenCalled();
  });

  test.each([
    { ...sharedConnector, kind: 'native' as const, label: 'Native' },
    { ...sharedConnector, kind: 'openapi' as const, label: 'OpenAPI' },
    { ...sharedConnector, label: 'MCP server' },
    { ...personalConnector, label: 'MCP server' }
  ])('connector detail preserves $kind terminology without administrative controls', ({ label, ...connector }): void => {
    const body = render(ConnectorDetail, { props: { connector } }).body;
    expect(body).toContain(connector.display_name);
    expect(body).toContain(label);
    expect(body).toContain('aria-hidden="true"');
    expect(body).toContain(connector.capability_description);
    expect(body).toMatch(new RegExp(`Authorization[\\s\\S]*?${connector.ownership === 'personal' ? 'Personal' : 'Shared'}`));
    expect(body).toContain(`${connector.capabilities.length} available`);
    expect(body).toContain('Organisation-managed');
    expect(body).toContain('Your organisation controls connector settings and available capabilities.');
    expect(body).not.toContain('Admin-managed');
    expect(body).not.toContain('User-managed');
    if (connector.ownership === 'personal') {
      expect(body).toContain('You authorize access using your own account.');
    } else {
      expect(body).not.toContain('You authorize access using your own account.');
    }
    expect(body).not.toContain('Personal access');
    expect(body).not.toMatch(/Publish|Unpublish|Published|Unpublished/);
    expect(body).not.toContain('Configure');
    expect(body).not.toContain('Edit connector');
    expect(body).not.toContain('Delete connector');
    expect(body).not.toContain('href="/admin');
    if (connector.kind !== 'downstream_mcp') expect(body).not.toContain('MCP server');
  });

  test('detail only offers management navigation when a management URL is supplied', (): void => {
    const body = render(ConnectorDetail, { props: { connector: sharedConnector, manageHref: '/admin/connectors/downstream_mcp/shared' } }).body;
    expect(body).toContain('href="/admin/connectors/downstream_mcp/shared"');
    expect(body).not.toMatch(/Publish|Unpublish|Published|Unpublished/);
    expect(body).not.toContain('Edit connector');
  });

  test('workspace lists shared and personal connectors together with only the selected detail', async (): Promise<void> => {
    const state = await loadedController();
    const body = render(ConnectorWorkspace, { props: { state } }).body;
    expect(body).toContain(sharedConnector.display_name);
    expect(body).toContain(personalConnector.display_name);
    expect(body).toContain(sharedConnector.capability_description);
    expect(body).not.toContain(personalConnector.capability_description);
    expect(body).not.toContain('aria-label="Personal access"');
    expect(body).not.toContain('href="/admin');
    expect(body).not.toContain('Shared connectors');
    expect(body).not.toContain('Personal connectors');
    expect(body).toContain('Personal authorization');
    expect(body).toContain('Shared authorization');
    expect(body.match(/Organisation-managed/g)).toHaveLength(3);
    expect(body).not.toContain('Admin-managed');
    expect(body).not.toContain('User-managed');
  });

  test('selected personal connector embeds its existing personal access controls', async (): Promise<void> => {
    const state = await loadedController();
    state.selectConnector('downstream_mcp:calendar');
    await state.personalCard('calendar')!.start();
    const body = render(ConnectorWorkspace, { props: { state } }).body;
    expect(body).toContain(personalConnector.capability_description);
    expect(body).not.toContain(sharedConnector.capability_description);
    expect(body).toContain('aria-label="Personal access"');
    expect(body).toContain('Continue sign-in');
    expect(body).toContain('Personal access actions for Calendar');
    expect(body).not.toContain('Cancel sign-in');
    expect(body).not.toContain('href="/admin');
  });

  test('workspace management permission exposes a link without exposing editing or publication controls', async (): Promise<void> => {
    const state = await loadedController();
    const body = render(ConnectorWorkspace, { props: { state, canManage: true } }).body;
    expect(body).toContain('href="/admin');
    expect(body).not.toMatch(/Publish|Unpublish|Published|Unpublished/);
    expect(body).not.toContain('Edit connector');
    expect(body).not.toContain('Delete connector');
  });

  test('capability tabs count resource templates with resources and initially show only tool descriptions', (): void => {
    const capabilities: CatalogueCapability[] = [
      { kind: 'tool', key: 'events', name: 'Events', description: 'Read calendar events', input_schema: {}, output_schema: { status: 'absent' } },
      { kind: 'prompt', key: 'agenda', name: 'Agenda', description: 'Prepare an agenda' },
      { kind: 'resource', key: 'calendar', name: 'Calendar', description: 'Calendar resource description' },
      { kind: 'resource_template', key: 'event', name: 'Event', description: 'Event template description' }
    ];
    const body = render(CatalogueCapabilities, { props: { capabilities } }).body;
    expect(body).toMatch(/<button[^>]*>[\s\S]*?Tools[\s\S]*?1[\s\S]*?<\/button>/);
    expect(body).toMatch(/<button[^>]*>[\s\S]*?Prompts[\s\S]*?1[\s\S]*?<\/button>/);
    expect(body).toMatch(/<button[^>]*>[\s\S]*?Resources[\s\S]*?2[\s\S]*?<\/button>/);
    expect(body).toContain('Read calendar events');
    expect(body).not.toContain('Prepare an agenda');
    expect(body).not.toContain('Calendar resource description');
    expect(body).not.toContain('Event template description');
  });
});
