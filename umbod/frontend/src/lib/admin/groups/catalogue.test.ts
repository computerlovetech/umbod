import { describe, expect, it, vi } from 'vitest';
import { InMemoryGroupCatalogue } from './in-memory';
import { GroupsRoute } from './http-route';
import type { GroupCatalogue } from './port';
import { groupCatalogueResponseSchema, registerGroupSchema } from './domain/schemas';
import { AdminApi } from '../infrastructure/admin-api';
import { browserTransport, HttpError, SchemaValidationError, type Transport, type TransportRequest } from '../infrastructure/transport';
import { InMemoryPublicConfigurationProvider } from '../infrastructure/public-configuration';

function httpCatalogue(fetch: typeof globalThis.fetch): GroupCatalogue {
  return new GroupsRoute(browserTransport({ fetch, configuration: new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' }) }));
}

describe('group catalogue port', () => {
  it('registers idempotently using exact nonblank values and grants no permissions', async (): Promise<void> => {
    const catalogue: GroupCatalogue = new InMemoryGroupCatalogue();
    await catalogue.register(' team ');
    await catalogue.register(' team ');
    await catalogue.register('team');
    await catalogue.register('Team');
    expect(await catalogue.list()).toEqual([{ group_id: ' team ' }, { group_id: 'team' }, { group_id: 'Team' }]);
    await catalogue.delete('team');
    expect(await catalogue.list()).toEqual([{ group_id: ' team ' }, { group_id: 'Team' }]);
  });
  it.each(['', ' ', '\n'])('rejects blank group ID %j', async (id): Promise<void> => {
    const catalogue: GroupCatalogue = new InMemoryGroupCatalogue();
    await expect(catalogue.register(id)).rejects.toThrow();
    expect(await catalogue.list()).toEqual([]);
  });
  it('returns isolated snapshots', async (): Promise<void> => {
    const catalogue: GroupCatalogue = new InMemoryGroupCatalogue([{ group_id: 'team' }]);
    (await catalogue.list())[0].group_id = 'changed';
    expect(await catalogue.list()).toEqual([{ group_id: 'team' }]);
  });
});

describe('shared registry HTTP boundary', () => {
  it('uses one route for connector compatibility delegates and the public catalogue', async (): Promise<void> => {
    const calls: TransportRequest<unknown>[] = [];
    const transport: Transport = { request: async <T>(request: TransportRequest<T>): Promise<T> => {
      calls.push(request);
      return (request.method === 'GET' ? { groups: [{ group_id: ' exact / group ' }] } : undefined) as T;
    } };
    const api = new AdminApi(transport);
    expect(api.groupPermissions.groups).toBe(api.groups);
    expect(await api.groupPermissions.permissions.list()).toEqual([{ groupId: ' exact / group ' }]);
    await api.groupPermissions.permissions.register(' exact / group ');
    await api.groupPermissions.permissions.delete(' exact / group ');
    expect(calls).toHaveLength(3);
    expect(calls[0]).toMatchObject({ method: 'GET', path: '/admin/groups', outputSchema: groupCatalogueResponseSchema });
    expect(calls[1]).toMatchObject({ method: 'POST', path: '/admin/groups', body: { group_id: ' exact / group ' }, inputSchema: registerGroupSchema });
    expect(calls[2]).toMatchObject({ method: 'DELETE', path: '/admin/groups', body: { group_id: ' exact / group ' }, inputSchema: registerGroupSchema });
  });
  it('validates outbound registration before HTTP and handles 204 with an exact JSON body', async (): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>(async () => new Response(null, { status: 204 }));
    const catalogue = httpCatalogue(fetch);
    await expect(catalogue.register(' ')).rejects.toBeInstanceOf(SchemaValidationError);
    expect(fetch).not.toHaveBeenCalled();
    await catalogue.register(' group ');
    expect(fetch).toHaveBeenCalledWith('/api/admin/groups', expect.objectContaining({ method: 'POST', body: '{"group_id":" group "}' }));
    await catalogue.delete(' group ');
    expect(fetch).toHaveBeenLastCalledWith('/api/admin/groups', expect.objectContaining({ method: 'DELETE', body: '{"group_id":" group "}' }));
  });
  it('preserves observed legacy IDs without allowing blank registration', async (): Promise<void> => {
    const groups = [{ group_id: '' }, { group_id: ' ' }];
    const catalogue = httpCatalogue(async () => new Response(JSON.stringify({ groups })));
    expect(await catalogue.list()).toEqual(groups);
    expect(await new InMemoryGroupCatalogue(groups).list()).toEqual(groups);
  });
  it('rejects malformed catalogue responses', async (): Promise<void> => {
    const catalogue = httpCatalogue(async () => new Response(JSON.stringify({ groups: [{ group_id: 123 }] })));
    await expect(catalogue.list()).rejects.toBeInstanceOf(SchemaValidationError);
  });
  it('propagates deletion conflicts for references without modifying the catalogue locally', async (): Promise<void> => {
    const catalogue = httpCatalogue(async () => new Response(JSON.stringify({ detail: 'Group is referenced' }), { status: 409 }));
    await expect(catalogue.delete('team')).rejects.toMatchObject({ status: 409 });
    await expect(catalogue.delete('team')).rejects.toBeInstanceOf(HttpError);
  });
});
