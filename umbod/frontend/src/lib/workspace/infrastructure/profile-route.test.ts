import { describe, expect, test, vi } from 'vitest';
import { browserTransport, type Transport, type TransportRequest } from '$lib/admin/infrastructure/transport';
import { InMemoryPublicConfigurationProvider } from '$lib/admin/infrastructure/public-configuration';
import { workspaceProfileSchema } from '../domain/profile';
import { WorkspaceAccessState } from '../workspace-access-state.svelte';
import { workspaceNavigation } from '../navigation';
import { ProfileRoute } from './profile-route';
import { HttpWorkspaceApi } from './workspace-api';

const profile = { user: { id: 'user-1', name: 'Alex', email: null, picture: null }, capabilities: { administration: false } };

describe('workspace profile transport', () => {
  test('declares the neutral profile GET and response schema through the transport port', async (): Promise<void> => {
    const calls: TransportRequest<unknown>[] = [];
    const transport: Transport = {
      async request<T>(options: TransportRequest<T>): Promise<T> {
        calls.push(options);
        if (!options.outputSchema) throw new Error('Missing output schema');
        return options.outputSchema.parse(profile);
      }
    };
    await expect(new ProfileRoute(transport).get()).resolves.toEqual(profile);
    expect(calls).toEqual([{ method: 'GET', path: '/me/profile', outputSchema: workspaceProfileSchema }]);
  });

  test.each(['/api', 'https://api.example.test/api/'])('ordinary identity uses configured base %s and never requests admin users', async (apiBaseUrl): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json(profile));
    const api = new HttpWorkspaceApi(browserTransport({
      fetch: request,
      configuration: new InMemoryPublicConfigurationProvider({ apiBaseUrl, mcpBaseUrl: '/mcp' })
    }));
    const access = new WorkspaceAccessState(api);
    await access.load();
    expect(access.accountIdentity).toMatchObject({ kind: 'visible', name: 'Alex', email: null, picture: null });
    expect(access.adminAccess).toBe('denied');
    expect(workspaceNavigation(access.adminAccess === 'allowed').some((item) => item.href.startsWith('/admin'))).toBe(false);
    expect(request).toHaveBeenCalledExactlyOnceWith(apiBaseUrl.replace(/\/$/, '') + '/me/profile', expect.objectContaining({ method: 'GET', credentials: 'same-origin' }));
    expect(request.mock.calls.some(([url]) => String(url).includes('/admin/users'))).toBe(false);
    access.dispose();
  });

  test('malformed capability fails at the shared transport boundary', async (): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ user: profile.user, capabilities: {} }));
    const api = new HttpWorkspaceApi(browserTransport({
      fetch: request,
      configuration: new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' })
    }));
    await expect(api.profile.get()).rejects.toMatchObject({ name: 'SchemaValidationError', direction: 'inbound' });
  });
});
