import { describe, expect, it, vi } from 'vitest';
import { InMemoryGroupCatalogue } from './in-memory';
import { GroupsRoute } from './http-route';
import type { GroupCatalogue } from './port';
import { groupCatalogueResponseSchema, registerGroupSchema, deleteGroupSchema } from './domain/schemas';
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
    expect(await catalogue.list()).toEqual([{ group_id: ' team ', label: ' team ', description: '', revision: 1 }, { group_id: 'team', label: 'team', description: '', revision: 1 }, { group_id: 'Team', label: 'Team', description: '', revision: 1 }]);
    await catalogue.delete('team');
    expect(await catalogue.list()).toEqual([{ group_id: ' team ', label: ' team ', description: '', revision: 1 }, { group_id: 'Team', label: 'Team', description: '', revision: 1 }]);
  });
  it.each(['', ' ', '\n'])('rejects blank group ID %j', async (id): Promise<void> => {
    const catalogue: GroupCatalogue = new InMemoryGroupCatalogue();
    await expect(catalogue.register(id)).rejects.toThrow();
    expect(await catalogue.list()).toEqual([]);
  });
  it('returns isolated snapshots', async (): Promise<void> => {
    const catalogue: GroupCatalogue = new InMemoryGroupCatalogue([{ group_id: 'team', label: 'team', description: '', revision: 1 }]);
    (await catalogue.list())[0].group_id = 'changed';
    expect(await catalogue.list()).toEqual([{ group_id: 'team', label: 'team', description: '', revision: 1 }]);
  });
});

describe('metadata contracts', () => {
  it('creates and revision-checks metadata while retaining the exact ID', async (): Promise<void> => {
    const catalogue = new InMemoryGroupCatalogue();
    const group = { group_id: ' /../exact ', label: ' Operators ', description: 'Reports' };
    await catalogue.create(group);
    await catalogue.create({ ...group, label: 'Different label', description: 'Different description' });
    expect(await catalogue.list()).toEqual([{ ...group, label: 'Operators', revision: 1 }]);
    await expect(catalogue.update({ ...group, expected_revision: 2 })).rejects.toMatchObject({ status: 409 });
    await expect(catalogue.update({ ...group, group_id: 'absent', expected_revision: 1 })).rejects.toMatchObject({ status: 404 });
    await expect(catalogue.update({ ...group, label: ' Readers ', expected_revision: 1 })).resolves.toEqual({ ...group, label: 'Readers', revision: 2 });
  });
  it.each(['.', '..', ' /../claim/ ', 'group?x=#%'])('uses a body-ID PUT and ID-only DELETE for %j', async (group_id): Promise<void> => {
    const group = { group_id, label: 'Label', description: '', revision: 2 };
    const fetch = vi.fn<typeof globalThis.fetch>(async (_url, init) => init?.method === 'PUT' ? new Response(JSON.stringify(group)) : new Response(null, { status: 204 }));
    const catalogue = httpCatalogue(fetch);
    await catalogue.create({ group_id, label: ' Label ', description: '' });
    expect(fetch).toHaveBeenLastCalledWith('/api/admin/groups', expect.objectContaining({ method: 'POST', body: JSON.stringify({ label: 'Label', description: '', group_id }) }));
    expect(await catalogue.update({ group_id, label: ' Label ', description: '', expected_revision: 1 })).toEqual(group);
    expect(fetch).toHaveBeenLastCalledWith('/api/admin/groups', expect.objectContaining({ method: 'PUT', body: JSON.stringify({ label: 'Label', description: '', group_id, expected_revision: 1 }) }));
    await catalogue.delete(group_id);
    expect(fetch).toHaveBeenLastCalledWith('/api/admin/groups', expect.objectContaining({ method: 'DELETE', body: JSON.stringify({ group_id }) }));
  });
  it.each([
    { label: '', description: '' },
    { label: ' ', description: '' },
    { label: 'x'.repeat(201), description: '' },
    { label: 'Valid', description: 'x'.repeat(2001) }
  ])('rejects invalid explicit metadata before dispatch', async (metadata): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>();
    await expect(httpCatalogue(fetch).create({ group_id: 'exact', ...metadata })).rejects.toBeInstanceOf(SchemaValidationError);
    expect(fetch).not.toHaveBeenCalled();
  });
  it.each(['', ' ', '\n'])('updates preserved blank legacy ID %j without permitting its creation', async (group_id): Promise<void> => {
    const catalogue = new InMemoryGroupCatalogue([{ group_id, label: group_id, description: '', revision: 1 }]);
    await expect(catalogue.create({ group_id, label: 'Repaired label', description: '' })).rejects.toThrow();
    await expect(catalogue.update({ group_id, label: 'Repaired label', description: '', expected_revision: 1 })).resolves.toEqual({ group_id, label: 'Repaired label', description: '', revision: 2 });
  });
  it('accepts legacy labels verbatim and rejects nonpositive revisions', async (): Promise<void> => {
    const label = ' legacy '.repeat(100);
    const group = { group_id: label, label, description: '', revision: 1 };
    const catalogue = httpCatalogue(async () => new Response(JSON.stringify({ groups: [group] })));
    expect(await catalogue.list()).toEqual([group]);
    const invalid = httpCatalogue(async () => new Response(JSON.stringify({ ...group, revision: 0 })));
    await expect(invalid.update({ group_id: label, label: 'New', description: '', expected_revision: 1 })).rejects.toBeInstanceOf(SchemaValidationError);
  });
});

describe('shared registry HTTP boundary', () => {
  it('uses one route for connector compatibility delegates and the public catalogue', async (): Promise<void> => {
    const calls: TransportRequest<unknown>[] = [];
    const transport: Transport = { request: async <T>(request: TransportRequest<T>): Promise<T> => {
      calls.push(request);
      return (request.method === 'GET' ? { groups: [{ group_id: ' exact / group ', label: 'exact / group', description: '', revision: 1 }] } : undefined) as T;
    } };
    const api = new AdminApi(transport);
    expect(api.groupPermissions.groups).toBe(api.groups);
    expect(await api.groupPermissions.permissions.list()).toEqual([{ groupId: ' exact / group ', label: 'exact / group', description: '', revision: 1 }]);
    await api.groupPermissions.permissions.register(' exact / group ');
    await api.groupPermissions.permissions.delete(' exact / group ');
    expect(calls).toHaveLength(3);
    expect(calls[0]).toMatchObject({ method: 'GET', path: '/admin/groups', outputSchema: groupCatalogueResponseSchema });
    expect(calls[1]).toMatchObject({ method: 'POST', path: '/admin/groups', body: { group_id: ' exact / group ' }, inputSchema: registerGroupSchema });
    expect(calls[2]).toMatchObject({ method: 'DELETE', path: '/admin/groups', body: { group_id: ' exact / group ' }, inputSchema: deleteGroupSchema });
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
    const groups = [{ group_id: '', label: 'Legacy group', description: '', revision: 1 }, { group_id: ' ', label: 'Legacy group', description: '', revision: 1 }];
    const catalogue = httpCatalogue(async () => new Response(JSON.stringify({ groups })));
    expect(await catalogue.list()).toEqual(groups);
    expect(await new InMemoryGroupCatalogue(groups).list()).toEqual(groups);
  });
  it.each(['', ' '])('deletes exact blank legacy ID %j with an ID-only body', async (group_id): Promise<void> => {
    const catalogue = new InMemoryGroupCatalogue([{ group_id, label: group_id, description: '', revision: 1 }]);
    await catalogue.delete(group_id);
    expect(await catalogue.list()).toEqual([]);
    const fetch = vi.fn<typeof globalThis.fetch>(async () => new Response(null, { status: 204 }));
    await httpCatalogue(fetch).delete(group_id);
    expect(fetch).toHaveBeenCalledExactlyOnceWith('/api/admin/groups', expect.objectContaining({ method: 'DELETE', body: JSON.stringify({ group_id }) }));
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
