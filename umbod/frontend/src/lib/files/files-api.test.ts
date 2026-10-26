import { describe, expect, test, vi } from 'vitest';
import { z } from 'zod';
import { browserTransport, AuthenticationRequiredError, HttpError, SchemaValidationError } from '$lib/admin/infrastructure/transport';
import { InMemoryPublicConfigurationProvider } from '$lib/admin/infrastructure/public-configuration';
import type { FilesApi } from './api';
import { childrenSchema, createFolderSchema, nodeSummarySchema } from './domain/schemas';
import { FilesApi as HttpFilesApi } from './infrastructure/files-api';
import { InMemoryFilesApi } from './infrastructure/in-memory-api';
import { fileId, filesystemFixture, filesystemNode, folderId, rootId } from './fixtures.test-support';

const input = { name: 'New folder', metadata: { content_type: {}, attributes: {} } };
const configuration = new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' });

describe('filesystem port', () => {
  test('browses root, directories and files and creates only folders', async (): Promise<void> => {
    const api: FilesApi = new InMemoryFilesApi(rootId, filesystemFixture);
    expect((await api.filesystem.getRoot()).parent_id).toEqual({});
    expect((await api.filesystem.getNode(fileId)).kind).toBe('file');
    expect((await api.filesystem.listChildren(rootId)).map((node) => node.id)).toEqual([folderId]);
    const created = await api.filesystem.createFolder(rootId, input);
    expect(created).toMatchObject({ parent_id: rootId, kind: 'directory', metadata: input.metadata });
    expect(await api.filesystem.listChildren(rootId)).toContainEqual(created);
    await expect(api.filesystem.createFolder(rootId, input)).rejects.toMatchObject({ status: 409 });
    await expect(api.filesystem.listChildren(fileId)).rejects.toMatchObject({ status: 400 });
    await expect(api.filesystem.getNode('00000000-0000-4000-8000-000000000099')).rejects.toMatchObject({ status: 404 });
  });
});

describe('filesystem schemas', () => {
  test('accepts exact core root, unspecified metadata and file content type', (): void => {
    expect(filesystemFixture.map((node) => nodeSummarySchema.parse(node))).toEqual(filesystemFixture);
    expect(nodeSummarySchema.parse(filesystemNode({ created_at: '2026-01-01T10:00:00' })).created_at).toBe('2026-01-01T10:00:00');
  });

  test.each([
    { id: 'not-a-uuid' }, { kind: 'symlink' }, { parent_id: null }, { parent_id: { id: rootId } },
    { revision: 0 }, { updated_at: 'yesterday' }, { metadata: { content_type: null, attributes: {} } },
    { metadata: { content_type: { guessed: true }, attributes: {} } },
    { metadata: { content_type: {}, attributes: { size: 12 } } }
  ])('rejects malformed payload %j', (override): void => {
    expect(nodeSummarySchema.safeParse({ ...filesystemFixture[0], ...override }).success).toBe(false);
  });

  test.each(['', ' ', '.', '..', 'a/b', 'a\\b'])('rejects invalid folder name %j', (name): void => {
    expect(createFolderSchema.safeParse({ ...input, name }).success).toBe(false);
  });

  test('rejects null outbound metadata and malformed list envelopes', (): void => {
    expect(createFolderSchema.safeParse({ ...input, metadata: { content_type: null, attributes: {} } }).success).toBe(false);
    expect(childrenSchema.safeParse({ nodes: [null] }).success).toBe(false);
    expect(childrenSchema.safeParse([]).success).toBe(false);
  });
});

describe('filesystem HTTP boundary', () => {
  test('uses only the four implemented user operations with validated bodies', async (): Promise<void> => {
    const request = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json(filesystemFixture[0]))
      .mockResolvedValueOnce(Response.json(filesystemFixture[1]))
      .mockResolvedValueOnce(Response.json({ nodes: [filesystemFixture[1]] }))
      .mockResolvedValueOnce(Response.json(filesystemNode({ id: fileId, parent_id: rootId, name: input.name }), { status: 201 }));
    const api: FilesApi = new HttpFilesApi(browserTransport({ fetch: request, configuration }));
    await api.filesystem.getRoot();
    await api.filesystem.getNode(folderId);
    await api.filesystem.listChildren(rootId);
    await api.filesystem.createFolder(rootId, input);
    expect(request.mock.calls.map(([url]) => url)).toEqual([
      '/api/me/filesystem/root', '/api/me/filesystem/nodes/' + folderId,
      '/api/me/filesystem/nodes/' + rootId + '/children', '/api/me/filesystem/nodes/' + rootId + '/directories'
    ]);
    expect(request.mock.calls.map(([, init]) => init?.method)).toEqual(['GET', 'GET', 'GET', 'POST']);
    expect(request.mock.calls[3][1]?.body).toBe(JSON.stringify(input));
    expect(request.mock.calls[3][1]?.credentials).toBe('same-origin');
  });

  test('rejects outbound data before a network call and malformed inbound nodes', async (): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ invalid: true }));
    const api: FilesApi = new HttpFilesApi(browserTransport({ fetch: request, configuration }));
    await expect(api.filesystem.createFolder(rootId, { ...input, name: '' })).rejects.toMatchObject({ direction: 'outbound' });
    expect(request).not.toHaveBeenCalled();
    await expect(api.filesystem.getRoot()).rejects.toBeInstanceOf(SchemaValidationError);
    expect(() => api.filesystem.getNode('invalid')).toThrow(z.ZodError);
    expect(request).toHaveBeenCalledTimes(1);
  });

  test.each([403, 404, 409, 500])('preserves HTTP %s without replay', async (status): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ detail: 'private' }, { status }));
    const api: FilesApi = new HttpFilesApi(browserTransport({ fetch: request, configuration }));
    await expect(api.filesystem.createFolder(rootId, input)).rejects.toBeInstanceOf(HttpError);
    expect(request).toHaveBeenCalledTimes(1);
  });

  test('keeps rejected authentication explicit', async (): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 401 }));
    const api: FilesApi = new HttpFilesApi(browserTransport({ fetch: request, configuration }));
    await expect(api.filesystem.getRoot()).rejects.toBeInstanceOf(AuthenticationRequiredError);
    expect(request).toHaveBeenCalledTimes(1);
  });
});
