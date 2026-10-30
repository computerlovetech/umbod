import { describe, expect, it, vi } from 'vitest';
import { browserTransport, SchemaValidationError } from '$lib/admin/infrastructure/transport';
import { IdentityDirectoryApi } from './api';
import { InMemoryIdentityDirectory } from './in-memory.test-support';

const directory = { issuer: 'issuer', claim: 'teams', groups: [{ value: ' / Exact ', first_seen_at: '2026-01-01T00:00:00Z', last_seen_at: '2026-02-01T00:00:00Z' }], has_more: false };

describe('identity directory port and HTTP validation', () => {
  it('keeps exact observed values separate from observations and supports bounded search', async (): Promise<void> => {
    const api = new InMemoryIdentityDirectory(directory);
    await api.observe();
    expect(api.observations).toBe(1);
    expect(await api.list({ query: 'EXACT', limit: 50 })).toEqual(directory);
    expect((await api.list({ query: 'absent', limit: 50 })).groups).toEqual([]);
    await expect(api.list({ query: '', limit: 101 })).rejects.toThrow();
  });
  it('uses shared transport for a bodyless observation and server-scoped search', async (): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValueOnce(new Response(null, { status: 204 })).mockResolvedValueOnce(Response.json(directory));
    const api = new IdentityDirectoryApi(browserTransport({ fetch: request, configuration: { get: async () => ({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' }) } }));
    await api.observations.observe();
    expect(request.mock.calls[0][0]).toBe('/api/me/identity-observations');
    expect(request.mock.calls[0][1]?.body).toBeUndefined();
    expect(request.mock.calls[0][1]?.headers).not.toHaveProperty('content-type');
    expect(await api.groups.list({ query: ' / Exact ', limit: 50 })).toEqual(directory);
    expect(request.mock.calls[1][0]).toBe('/api/admin/identity-directory/groups?query=+%2F+Exact+&limit=50');
    expect(() => api.groups.list({ query: '', limit: 101 })).toThrow();
    expect(request).toHaveBeenCalledTimes(2);
  });
  it.each([{ ...directory, groups: [{ ...directory.groups[0], last_seen_at: 'invalid' }] }, { ...directory, has_more: 'false' }])('rejects malformed responses', async (payload): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json(payload));
    const api = new IdentityDirectoryApi(browserTransport({ fetch: request, configuration: { get: async () => ({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' }) } }));
    await expect(api.groups.list({ query: '', limit: 50 })).rejects.toBeInstanceOf(SchemaValidationError);
  });
});
