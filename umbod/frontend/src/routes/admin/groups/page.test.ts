import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'svelte/server';
import { Window } from 'happy-dom';
import { load } from './+page';
import GroupsPage from './+page.svelte';
import { publicConfigurationProvider } from '$lib/admin/infrastructure/public-configuration';
import { AuthenticationRequiredError, SchemaValidationError } from '$lib/admin/infrastructure/transport';
import { workspaceNavigation } from '$lib/workspace/navigation';

vi.mock('$app/state', () => ({ navigating: { to: null, from: null }, page: { url: new URL('https://umbod.test/admin/groups') } }));
afterEach((): void => { vi.restoreAllMocks(); });

describe('groups route', () => {
  it('loads validated metadata without loading permission inventories', async (): Promise<void> => {
    vi.spyOn(publicConfigurationProvider, 'get').mockResolvedValue({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' });
    const groups = [{ group_id: ' /../exact ', label: 'Operators', description: 'Report owners', revision: 2 }];
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(new Response(JSON.stringify({ groups })));
    await expect(load({ fetch } as never)).resolves.toEqual({ groups });
    expect(fetch).toHaveBeenCalledExactlyOnceWith('/api/admin/groups', expect.objectContaining({ method: 'GET' }));
  });
  it('rejects malformed catalogue responses', async (): Promise<void> => {
    vi.spyOn(publicConfigurationProvider, 'get').mockResolvedValue({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' });
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(new Response(JSON.stringify({ groups: [{ group_id: 'exact', label: 'Label', description: '', revision: 0 }] })));
    await expect(load({ fetch } as never)).rejects.toBeInstanceOf(SchemaValidationError);
  });
  it.each([401, 403])('preserves authorization failure %s', async (status): Promise<void> => {
    vi.spyOn(publicConfigurationProvider, 'get').mockResolvedValue({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' });
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(new Response('{}', { status }));
    if (status === 401) await expect(load({ fetch } as never)).rejects.toBeInstanceOf(AuthenticationRequiredError);
    else await expect(load({ fetch } as never)).rejects.toMatchObject({ status: 403 });
  });
  it('renders a dedicated active destination in the authorized workspace only', (): void => {
    const body = render(GroupsPage, { props: { data: { groups: [], accountIdentity: { kind: 'hidden' } } } }).body;
    const document = new Window().document;
    document.body.innerHTML = body;
    expect(document.querySelector('h1')?.textContent).toBe('Groups');
    expect(body).not.toContain('admin-eyebrow');
    expect(document.querySelector('nav[aria-label="Workspace navigation"] a[aria-current="page"]')?.getAttribute('href')).toBe('/admin/groups');
    expect(workspaceNavigation(false).some((item) => item.href === '/admin/groups')).toBe(false);
    expect(workspaceNavigation(true).some((item) => item.href === '/admin/groups')).toBe(true);
  });
});
