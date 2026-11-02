import { describe, expect, test, vi } from 'vitest';
import { browserTransport } from '$lib/admin/infrastructure/transport';
import { InMemoryPublicConfigurationProvider } from '$lib/admin/infrastructure/public-configuration';
import { FilesApi } from './infrastructure/files-api';
import { InMemoryFilesApi } from './infrastructure/in-memory-api.test-support';
import { fileId, filesystemFixture, filesystemNode, folderId, rootId } from './fixtures.test-support';
import { updateNodeSchema } from './domain/schemas';

const destinationId = '00000000-0000-4000-8000-000000000004';
const destination = filesystemNode({ id: destinationId, parent_id: rootId, name: 'Destination' });

function memory(): InMemoryFilesApi { return new InMemoryFilesApi(rootId, [...filesystemFixture, destination]); }

describe('atomic node updates', (): void => {
  test('sends all changes in one PATCH with quoted revision and validates before network', async (): Promise<void> => {
    const body = { name: 'Moved.txt', parent_id: rootId, metadata: { attributes: { description: 'Guidance' }, content_type: {} } };
    const returned = { ...filesystemFixture[2], ...body, metadata: { attributes: { topic: 'Planning', description: 'Guidance' }, content_type: {} }, revision: 2 };
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json(returned));
    const configuration = new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' });
    const api = new FilesApi(browserTransport({ origin: () => 'https://umbod.test', fetch: request, configuration }), () => 'https://umbod.test');
    expect(await api.filesystem.updateNode(fileId, 1, body)).toEqual(returned);
    const [path, init] = request.mock.calls[0];
    expect(path).toBe('/api/me/filesystem/nodes/' + fileId);
    expect(init?.method).toBe('PATCH');
    expect(new Headers(init?.headers).get('If-Match')).toBe('"1"');
    expect(JSON.parse(String(init?.body))).toEqual(body);
    await expect(api.filesystem.updateNode(fileId, 1, { name: '' })).rejects.toMatchObject({ direction: 'outbound' });
    expect(request).toHaveBeenCalledTimes(1);
  });

  test.each([{}, { name: null }, { parent_id: null }, { metadata: null }, { metadata: { attributes: null } }, { metadata: { content_type: null } }, { extra: 'x' }, { name: '/' }, { name: '..' }, { name: ' ' }, { metadata: { extra: 'x' } }])('rejects invalid patch %j', (input): void => {
    expect(updateNodeSchema.safeParse(input).success).toBe(false);
  });

  test('renames, moves and merges metadata once without changing identity or file bytes', async (): Promise<void> => {
    const api = memory();
    const uploaded = await api.filesystem.uploadFile(folderId, { file: new File(['unchanged'], 'Data.txt'), name: 'Data.txt' });
    const updated = await api.filesystem.updateNode(uploaded.id, 1, { name: 'Renamed.txt', parent_id: destinationId, metadata: { attributes: { description: 'New' } } });
    expect(updated).toMatchObject({ id: uploaded.id, kind: 'file', revision: 2, name: 'Renamed.txt', parent_id: destinationId });
    expect(updated.created_at).toBe(uploaded.created_at);
    expect(await api.filesystem.readContent(updated.id)).toEqual(new TextEncoder().encode('unchanged'));
    expect((await api.filesystem.listChildren(folderId)).some((node) => node.id === uploaded.id)).toBe(false);
  });

  test.each([fileId, folderId, destinationId])('requires independent discover and write on move participant %s', async (deniedId): Promise<void> => {
    for (const permission of ['read', 'write']) {
      const api = new InMemoryFilesApi(rootId, [...filesystemFixture, destination], undefined, undefined, (node) => permission !== 'read' || node.id !== deniedId, (node) => permission !== 'write' || node.id !== deniedId);
      await expect(api.filesystem.updateNode(fileId, 1, { name: 'Changed', parent_id: destinationId })).rejects.toMatchObject({ status: 403 });
    }
  });

  test('commits only one concurrent mutation for a captured revision', async (): Promise<void> => {
    const api = memory();
    const results = await Promise.allSettled([
      api.filesystem.updateNode(fileId, 1, { name: 'First', parent_id: destinationId }),
      api.filesystem.updateNode(fileId, 1, { name: 'Second', parent_id: rootId })
    ]);
    expect(results.filter((result) => result.status === 'fulfilled')).toHaveLength(1);
    expect(results.filter((result) => result.status === 'rejected')).toMatchObject([{ reason: { status: 412 } }]);
    expect((await api.filesystem.getNode(fileId)).revision).toBe(2);
  });

  test('rename does not require parent access and root remains a valid destination', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture, undefined, undefined, (node) => node.id !== folderId, (node) => node.id !== folderId);
    expect((await api.filesystem.updateNode(fileId, 1, { name: 'Independent' })).revision).toBe(2);
    expect((await memory().filesystem.updateNode(fileId, 1, { parent_id: rootId })).parent_id).toBe(rootId);
  });

  test('rejects collisions, cycles, root changes, wrong destinations and stale revisions without partial mutation', async (): Promise<void> => {
    const api = memory();
    const collision = await api.filesystem.createFolder(destinationId, { name: 'Notes.txt', metadata: { attributes: {}, content_type: {} } });
    await expect(api.filesystem.updateNode(fileId, 1, { parent_id: destinationId, metadata: { attributes: { description: 'Not applied' } } })).rejects.toMatchObject({ status: 409 });
    expect(await api.filesystem.getNode(fileId)).toEqual(filesystemFixture[2]);
    await expect(api.filesystem.updateNode(folderId, 1, { parent_id: folderId })).rejects.toMatchObject({ status: 409 });
    await expect(api.filesystem.updateNode(rootId, 1, { name: 'Root' })).rejects.toMatchObject({ status: 409 });
    await expect(api.filesystem.updateNode(rootId, 1, { parent_id: destinationId })).rejects.toMatchObject({ status: 409 });
    await expect(api.filesystem.updateNode(destinationId, 1, { parent_id: fileId })).rejects.toMatchObject({ status: 409 });
    await expect(api.filesystem.updateNode(fileId, 2, { name: 'Stale' })).rejects.toMatchObject({ status: 412 });
    await expect(api.filesystem.updateNode(destinationId, 1, { parent_id: collision.id })).rejects.toMatchObject({ status: 409 });
    await expect(api.filesystem.updateNode(crypto.randomUUID(), 1, { name: 'Missing' })).rejects.toMatchObject({ status: 403 });
  });
});
