import { describe, expect, test, vi } from 'vitest';
import { browserTransport, SchemaValidationError, type Transport, type TransportRequest } from '../infrastructure/transport';
import { NamespacesRoute } from './namespaces-route';
import { InMemoryPublicConfigurationProvider } from '../infrastructure/public-configuration';
import { createNamespaceSchema, updateNamespaceSchema, sharedNamespaceSchema } from './domain/namespaces';

class MemoryTransport implements Transport {
  readonly requests: TransportRequest<unknown>[] = [];
  request = async <T>(request: TransportRequest<T>): Promise<T> => {
    if (request.inputSchema) request.inputSchema.parse(request.body);
    this.requests.push(request);
    const entry = { id: '00000000-0000-4000-8000-000000000001', root_node_id: '00000000-0000-4000-8000-000000000002', name: 'Research', description: 'Shared research', root_revision: 3, revision: 1, groups: [] };
    return request.outputSchema!.parse(request.method === 'GET' ? { namespaces: [entry] } : entry);
  };
}

describe('namespace HTTP contract', () => {
  test('validates optional descriptions without defaulting access-only replacements', async (): Promise<void> => {
    const transport = new MemoryTransport();
    const api = new NamespacesRoute(transport);
    const entry = await api.create({ name: 'Research', groups: [], description: 'Read first\nThen explore' });
    expect(entry.description).toBe('Shared research');
    expect(entry.root_revision).toBe(3);
    await api.update(entry.id, { name: entry.name, groups: [], expected_revision: 1, description: '', expected_root_revision: 3 });
    expect(transport.requests[0].body).toMatchObject({ description: 'Read first\nThen explore' });
    expect(transport.requests[1].body).toMatchObject({ description: '', expected_root_revision: 3 });
    const accessOnly = updateNamespaceSchema.parse({ name: entry.name, groups: [], expected_revision: 1 });
    expect(accessOnly).not.toHaveProperty('description');
    expect(accessOnly).not.toHaveProperty('expected_root_revision');
    const { root_revision, ...missingRootRevision } = entry;
    const { description, ...missingDescription } = entry;
    expect(sharedNamespaceSchema.safeParse(missingRootRevision).success).toBe(false);
    expect(sharedNamespaceSchema.safeParse(missingDescription).success).toBe(false);
  });

  test.each([
    { expected_root_revision: 1 },
    { description: '' },
    { description: 'Changed' },
    { description: null, expected_root_revision: 1 },
    { description: 'Changed', expected_root_revision: null },
    { description: 'Changed', expected_root_revision: 0 }
  ])('blocks invalid description updates before transport submission', async (descriptionChange): Promise<void> => {
    const transport = new MemoryTransport();
    const api = new NamespacesRoute(transport);
    const input = { name: 'Research', groups: [], expected_revision: 1, ...descriptionChange };
    expect(updateNamespaceSchema.safeParse(input).success).toBe(false);
    await expect(api.update('00000000-0000-4000-8000-000000000001', input as Parameters<typeof api.update>[1])).rejects.toThrow();
    expect(transport.requests).toEqual([]);
  });

  test('rejects explicit null creation descriptions', (): void => {
    expect(createNamespaceSchema.safeParse({ name: 'Research', groups: [], description: null }).success).toBe(false);
  });

  test('uses validated list, creation and revision-safe replacement routes', async (): Promise<void> => {
    const transport = new MemoryTransport();
    const api = new NamespacesRoute(transport);
    const [entry] = await api.list();
    await api.create({ name: 'Research', groups: [] });
    await api.update(entry.id, { expected_revision: entry.revision, name: 'Research', groups: [] });
    expect(transport.requests.map(({ method, path, body }) => ({ method, path, body }))).toEqual([
      { method: 'GET', path: '/admin/filesystem/namespaces', body: undefined },
      { method: 'POST', path: '/admin/filesystem/namespaces', body: { name: 'Research', groups: [] } },
      { method: 'PUT', path: '/admin/filesystem/namespaces/' + entry.id, body: { expected_revision: 1, name: 'Research', groups: [] } }
    ]);
  });

  test('sends both deletion revisions as JSON and accepts a 204 without parsing JSON', async (): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(new Response(null, { status: 204 }));
    const configuration = new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' });
    const api = new NamespacesRoute(browserTransport({ fetch, configuration }));
    const id = '00000000-0000-4000-8000-000000000001';
    await expect(api.delete(id, { expected_revision: 2, expected_root_revision: 3 })).resolves.toBeUndefined();
    expect(fetch).toHaveBeenCalledExactlyOnceWith('/api/admin/filesystem/namespaces/' + id, expect.objectContaining({
      method: 'DELETE',
      headers: expect.objectContaining({ 'content-type': 'application/json' }),
      body: JSON.stringify({ expected_revision: 2, expected_root_revision: 3 })
    }));
  });

  test.each([
    { expected_revision: 0, expected_root_revision: 1 },
    { expected_revision: 1, expected_root_revision: 1.5 }
  ])('rejects invalid deletion revisions before fetch', async (revisions): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>();
    const api = new NamespacesRoute(browserTransport({ fetch }));
    await expect(api.delete('00000000-0000-4000-8000-000000000001', revisions)).rejects.toBeInstanceOf(SchemaValidationError);
    expect(fetch).not.toHaveBeenCalled();
  });

  test.each([
    { name: '', groups: [] },
    { name: 'Research', groups: [{ group_id: 'readers', access: 'share' }] },
    { name: 'Research', groups: [{ group_id: 'readers', access: 'read' }, { group_id: 'readers', access: 'read_write' }] },
    { name: 'Research', groups: [], owner: 'caller' }
  ])('rejects invalid or authority-bearing requests', (input): void => {
    expect(createNamespaceSchema.safeParse(input).success).toBe(false);
    expect(updateNamespaceSchema.safeParse({ ...input, expected_revision: 1 }).success).toBe(false);
  });
});
