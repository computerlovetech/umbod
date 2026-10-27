import { describe, expect, test, vi } from 'vitest';
import { z } from 'zod';
import { AdminApi } from '../infrastructure/admin-api';
import { InMemoryPublicConfigurationProvider } from '../infrastructure/public-configuration';
import { AuthenticationRequiredError, HttpError, NetworkError, SchemaValidationError, browserTransport, type Transport, type TransportRequest } from '../infrastructure/transport';
import { overviewFixture, overviewResponseFixture } from './fixtures.test-support';
import { OverviewRoute } from './http-route';
import { adminOverviewResponseSchema, unavailableOverview } from './models';
import type { OverviewSource } from './port';

function transport(request: typeof fetch): Transport {
  return browserTransport({
    fetch: request,
    configuration: new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' })
  });
}

describe('overview route', () => {
  test('declares a single GET and wire validation through the transport port', async () => {
    const calls: TransportRequest<unknown>[] = [];
    const fake: Transport = {
      async request<T>(options: TransportRequest<T>): Promise<T> {
        calls.push(options);
        if (!options.outputSchema) throw new Error('Missing output schema');
        return options.outputSchema.parse(overviewResponseFixture());
      }
    };
    const source: OverviewSource = new OverviewRoute(fake);
    expect(await source.load()).toEqual(overviewFixture());
    expect(calls).toEqual([{ method: 'GET', path: '/admin/overview', outputSchema: adminOverviewResponseSchema }]);
  });

  test.each([0, 1, 1000000])('fetches exactly once regardless of %i connectors and tools', async (count) => {
    const response = overviewResponseFixture(count);
    response.breakdown[1].tools = { status: 'unavailable' };
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json(response));
    const source: OverviewSource = new AdminApi(transport(request)).overview;
    const result = await source.load();
    expect(result).toEqual({ ...overviewFixture(count), breakdown: response.breakdown });
    expect(result).not.toHaveProperty('permission_groups');
    expect(request).toHaveBeenCalledExactlyOnceWith('/api/admin/overview', expect.objectContaining({ method: 'GET', credentials: 'same-origin' }));
  });

  test.each([404, 429, 500, 503])('returns all unavailable for HTTP %i', async (status) => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status }));
    expect(await new OverviewRoute(transport(request)).load()).toEqual(unavailableOverview());
    expect(request).toHaveBeenCalledOnce();
  });

  test('returns all unavailable for a network failure', async () => {
    const request = vi.fn<typeof fetch>().mockRejectedValue(new TypeError('offline'));
    expect(await new OverviewRoute(transport(request)).load()).toEqual(unavailableOverview());
    expect(request).toHaveBeenCalledOnce();
  });

  test.each([401, 403])('preserves HTTP authentication status %i', async (status) => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status }));
    await expect(new OverviewRoute(transport(request)).load()).rejects.toBeInstanceOf(status === 401 ? AuthenticationRequiredError : HttpError);
    expect(request).toHaveBeenCalledOnce();
  });

  test.each([{}, { ...overviewResponseFixture(), tools: { status: 'available', value: { enabled: -1, known: 0 } } }])('rejects malformed response without an unavailable fallback', async (response) => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json(response));
    await expect(new OverviewRoute(transport(request)).load()).rejects.toMatchObject({ name: 'SchemaValidationError', direction: 'inbound' });
    expect(request).toHaveBeenCalledOnce();
  });

  test('does not mask invalid JSON', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response('not json'));
    await expect(new OverviewRoute(transport(request)).load()).rejects.toBeInstanceOf(SyntaxError);
    expect(request).toHaveBeenCalledOnce();
  });

  test.each([
    new AuthenticationRequiredError(),
    new HttpError(401, 'Unauthorized', null),
    new HttpError(403, 'Forbidden', null),
    new SchemaValidationError('inbound', z.string().safeParse(0).error!.issues),
    new Error('programming failure')
  ])('preserves non-operational and authorization errors unchanged', async (failure) => {
    const fake: Transport = { request: async <T>(): Promise<T> => { throw failure; } };
    await expect(new OverviewRoute(fake).load()).rejects.toBe(failure);
  });

  test('recognizes a transport network error', async () => {
    const fake: Transport = { request: async <T>(): Promise<T> => { throw new NetworkError('offline'); } };
    expect(await new OverviewRoute(fake).load()).toEqual(unavailableOverview());
  });
});
