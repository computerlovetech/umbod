import { describe, expect, test, vi } from 'vitest';
import { z } from 'zod';
import { browserTransport, SchemaValidationError } from '$lib/admin/infrastructure/transport';
import { InMemoryPublicConfigurationProvider } from '$lib/admin/infrastructure/public-configuration';
import { FilesApi } from './infrastructure/files-api';
import { InMemoryNodeSharing } from './infrastructure/in-memory-sharing.test-support';
import { fileId } from './fixtures.test-support';
import type { NodeAccess } from './domain/sharing';

const configuration = new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' });
const view: NodeAccess = { node_id: fileId, revision: 'opaque-abc123', groups: [{ group_id: ' Team A ', permissions: ['discover', 'share'] }], blocked_group_ids: ['blocked'] };

describe('node sharing adapters', (): void => {
  test('in-memory default denies; configured access preserves exact IDs and revisions', async (): Promise<void> => {
    const sharing = new InMemoryNodeSharing();
    await expect(sharing.inspectAccess(fileId)).rejects.toMatchObject({ status: 403 });
    sharing.configure(view, [{ group_id: ' Team A ', label: 'Team A', description: 'Description' }, { group_id: 'blocked', label: 'Blocked', description: '' }]);
    expect(await sharing.listEligibleSharingGroups(fileId)).toEqual([{ group_id: ' Team A ', label: 'Team A', description: 'Description' }]);
    await expect(sharing.replaceAccess(fileId, 'stale', { groups: [] })).rejects.toMatchObject({ status: 412 });
    await expect(sharing.replaceAccess(fileId, view.revision, { groups: [{ group_id: 'unknown', permissions: ['read'] }] })).rejects.toMatchObject({ status: 422 });
    expect(await sharing.replaceAccess(fileId, view.revision, { groups: [] })).toMatchObject({ groups: [], blocked_group_ids: ['blocked'] });
  });

  test('HTTP sends only groups with strong opaque conditional JSON and reads the node-scoped catalogue', async (): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValueOnce(Response.json(view)).mockResolvedValueOnce(Response.json({ groups: [{ group_id: ' Team A ', label: 'Friendly', description: 'Exact provider group' }] })).mockResolvedValueOnce(Response.json({ ...view, revision: 'new-hash' }));
    const api = new FilesApi(browserTransport({ fetch, configuration }));
    const signal = new AbortController().signal;
    expect(await api.sharing.inspectAccess(fileId, signal)).toEqual(view);
    expect(await api.sharing.listEligibleSharingGroups(fileId, signal)).toEqual([{ group_id: ' Team A ', label: 'Friendly', description: 'Exact provider group' }]);
    expect(await api.sharing.replaceAccess(fileId, view.revision, { groups: view.groups })).toMatchObject({ revision: 'new-hash' });
    expect(fetch.mock.calls[0]).toEqual(['/api/me/filesystem/nodes/' + fileId + '/access', expect.objectContaining({ signal })]);
    expect(fetch.mock.calls[1][0]).toBe('/api/me/filesystem/nodes/' + fileId + '/access/eligible-groups');
    expect(fetch.mock.calls[2][1]).toMatchObject({ method: 'PUT', headers: { 'If-Match': '"opaque-abc123"', 'content-type': 'application/json' }, body: JSON.stringify({ groups: view.groups }) });
  });

  test.each(['*', 'W/"opaque"', '"one", "two"', '"bad\r\nvalue"', '"bad\u0000value"', '"bad\u007fvalue"', '""', 'unquoted', '"unterminated'])('blocks malformed If-Match %j before any fetch for JSON and absent bodies', async (tag): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>();
    const transport = browserTransport({ fetch, configuration });
    for (const body of [undefined, { groups: [] }]) {
      await expect(transport.request({ method: 'PUT', path: '/me/filesystem/nodes/' + fileId + '/access', body, inputSchema: z.strictObject({ groups: z.array(z.never()) }), conditionalHeaders: { 'If-Match': tag } })).rejects.toMatchObject({ direction: 'outbound' });
    }
    expect(fetch).not.toHaveBeenCalled();
  });

  test.each(['raw', 'multipart'] as const)('validates and forwards conditional headers consistently for %s bodies', async (kind): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(new Response(null, { status: 204 }));
    const transport = browserTransport({ fetch, configuration });
    const file = new File(['data'], 'payload.txt');
    const requestBody = kind === 'raw'
      ? { kind: 'raw' as const, value: file, schema: z.instanceof(File), headers: { 'content-type': 'text/plain' } }
      : { kind: 'multipart' as const, form: new FormData(), metadata: {}, metadataSchema: z.strictObject({}) };
    await expect(transport.request({ method: 'PUT', path: '/resource', requestBody, conditionalHeaders: { 'If-Match': 'W/"bad"' } })).rejects.toMatchObject({ direction: 'outbound' });
    expect(fetch).not.toHaveBeenCalled();
    await transport.request({ method: 'PUT', path: '/resource', requestBody, conditionalHeaders: { 'If-Match': '"opaque-revision"' } });
    expect(fetch.mock.calls[0][1]?.headers).toMatchObject({ 'If-Match': '"opaque-revision"' });
  });

  test('strictly rejects extra replacement fields and malformed authoritative output', async (): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(Response.json({ ...view, revision: 123 }));
    const api = new FilesApi(browserTransport({ fetch, configuration }));
    await expect(api.sharing.replaceAccess(fileId, view.revision, { groups: [], revision: 'in-body' } as unknown as { groups: [] })).rejects.toBeInstanceOf(SchemaValidationError);
    expect(fetch).not.toHaveBeenCalled();
    await expect(api.sharing.inspectAccess(fileId)).rejects.toMatchObject({ direction: 'inbound' });
  });
});
