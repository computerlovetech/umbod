import { afterEach, describe, expect, test, vi } from 'vitest';
import type { LayoutLoadEvent } from './$types';
import { load } from './+layout';

vi.mock('$lib/admin/infrastructure/public-configuration', () => ({
  publicConfigurationProvider: { get: async (): Promise<object> => ({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' }) }
}));

afterEach(() => vi.unstubAllGlobals());

describe('admin layout loader', () => {
  test.each([null, 'admin@example.test'])('accepts a successful profile with email %s', async (email) => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(Response.json({
      id: 'admin-123', email, name: 'unknown', picture: 'https://example.com/admin.png'
    }));
    await expect(load({ fetch } as unknown as LayoutLoadEvent)).resolves.toEqual({
      accountIdentity: {
        kind: 'visible', email, name: 'unknown', picture: 'https://example.com/admin.png',
        hiddenValues: { id: 'admin-123' }
      }
    });
  });

  test.each([
    [401, 'Your sign-in was not accepted by the API. Sign in again or contact your administrator.'],
    [403, 'You do not have permission to access this administration area. Contact your administrator.'],
    [503, 'Service Unavailable']
  ])('preserves status %s without navigation', async (status, message) => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(Response.json({ detail: 'private backend diagnostics' }, { status: Number(status), statusText: status === 503 ? 'Service Unavailable' : 'private status text' }));
    const assign = vi.fn();
    vi.stubGlobal('window', { location: { assign } });
    await expect(load({ fetch } as unknown as LayoutLoadEvent)).rejects.toMatchObject({ status, body: { message } });
    expect(fetch).toHaveBeenCalledOnce();
    expect(assign).not.toHaveBeenCalled();
  });
});
