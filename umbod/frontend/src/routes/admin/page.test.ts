import { describe, expect, test, vi } from 'vitest';
import { overviewFixture, overviewResponseFixture } from '$lib/admin/overview/fixtures.test-support';
import { unavailableOverview } from '$lib/admin/overview/models';
import { AuthenticationRequiredError, SchemaValidationError } from '$lib/admin/infrastructure/transport';
import type { PageLoadEvent } from './$types';
import { load } from './+page';

vi.mock('$lib/admin/infrastructure/public-configuration', () => ({
  publicConfigurationProvider: { get: async (): Promise<object> => ({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' }) }
}));

describe('admin overview page loader', () => {
  test('returns the summary from one focused request', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(Response.json(overviewResponseFixture(45)));
    await expect(load({ fetch } as unknown as PageLoadEvent)).resolves.toEqual({ overview: overviewFixture(45) });
    expect(fetch).toHaveBeenCalledExactlyOnceWith('/api/admin/overview', expect.objectContaining({ method: 'GET' }));
  });

  test.each([404, 500, 503])('renders unavailable on operational HTTP %i failures', async (status) => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(new Response(null, { status }));
    await expect(load({ fetch } as unknown as PageLoadEvent)).resolves.toEqual({ overview: unavailableOverview() });
    expect(fetch).toHaveBeenCalledOnce();
  });

  test('renders unavailable on network failures', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockRejectedValue(new TypeError('offline'));
    await expect(load({ fetch } as unknown as PageLoadEvent)).resolves.toEqual({ overview: unavailableOverview() });
    expect(fetch).toHaveBeenCalledOnce();
  });

  test('preserves authentication-required errors', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(new Response(null, { status: 401 }));
    await expect(load({ fetch } as unknown as PageLoadEvent)).rejects.toBeInstanceOf(AuthenticationRequiredError);
    expect(fetch).toHaveBeenCalledOnce();
  });

  test('preserves forbidden page errors', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(new Response(null, { status: 403, statusText: 'Forbidden' }));
    await expect(load({ fetch } as unknown as PageLoadEvent)).rejects.toMatchObject({ status: 403, body: { message: 'Forbidden' } });
    expect(fetch).toHaveBeenCalledOnce();
  });

  test('rejects invalid summaries instead of rendering unavailable', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(Response.json({}));
    await expect(load({ fetch } as unknown as PageLoadEvent)).rejects.toBeInstanceOf(SchemaValidationError);
    expect(fetch).toHaveBeenCalledOnce();
  });
});
