import { describe, expect, test, vi } from 'vitest';
import { z } from 'zod';
import { browserTransport, AuthenticationRequiredError, HttpError, SchemaValidationError } from '$lib/admin/infrastructure/transport';
import { InMemoryPublicConfigurationProvider } from '$lib/admin/infrastructure/public-configuration';
import type { FilesApi } from './api';
import { childrenSchema, createFolderSchema, fileNameSchema, fileUploadSchema, nodeSummarySchema, uploadPolicySchema, type FileUpload } from './domain/schemas';
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

describe('filesystem upload port', () => {
  test('exposes policy and creates a file with an explicit name and inferred metadata', async (): Promise<void> => {
    const api: FilesApi = new InMemoryFilesApi(rootId, filesystemFixture);
    expect(await api.filesystem.getUploadPolicy(rootId)).toEqual({ max_bytes: 10485760 });
    const created = await api.filesystem.uploadFile(rootId, {
      file: new File(['hello'], 'original.txt', { type: 'text/plain' }), name: 'Renamed.txt'
    });
    expect(created).toMatchObject({
      parent_id: rootId, name: 'Renamed.txt', kind: 'file', revision: 1,
      metadata: { content_type: 'text/plain', attributes: {} }
    });
    expect(await api.filesystem.getNode(created.id)).toEqual(created);
    expect(await api.filesystem.listChildren(rootId)).toContainEqual(created);
  });

  test('allows zero bytes and the size limit, rejecting larger files without creating nodes', async (): Promise<void> => {
    const api: FilesApi = new InMemoryFilesApi(rootId, filesystemFixture, { max_bytes: 2 });
    expect(await api.filesystem.getUploadPolicy(rootId)).toEqual({ max_bytes: 2 });
    const empty = await api.filesystem.uploadFile(rootId, { file: new File([], 'empty'), name: 'empty' });
    expect(empty.metadata.content_type).toBe('application/octet-stream');
    await api.filesystem.uploadFile(rootId, { file: new File(['ab'], 'limit'), name: 'limit' });
    await expect(api.filesystem.uploadFile(rootId, { file: new File(['abc'], 'large'), name: 'large' })).rejects.toMatchObject({ status: 413 });
    expect((await api.filesystem.listChildren(rootId)).map((node) => node.name)).toEqual(['Projects', 'empty', 'limit']);
  });

  test('rejects missing parents, file parents and directory or file name collisions', async (): Promise<void> => {
    const api: FilesApi = new InMemoryFilesApi(rootId, filesystemFixture);
    const upload = { file: new File([], 'original'), name: 'Projects' };
    const missingId = '00000000-0000-4000-8000-000000000099';
    await expect(api.filesystem.getUploadPolicy(missingId)).rejects.toMatchObject({ status: 404 });
    await expect(api.filesystem.getUploadPolicy(fileId)).rejects.toMatchObject({ status: 409 });
    await expect(api.filesystem.uploadFile(missingId, upload)).rejects.toMatchObject({ status: 404 });
    await expect(api.filesystem.uploadFile(fileId, upload)).rejects.toMatchObject({ status: 409 });
    await expect(api.filesystem.uploadFile(rootId, upload)).rejects.toMatchObject({ status: 409 });
    await expect(api.filesystem.uploadFile(folderId, { ...upload, name: 'Notes.txt' })).rejects.toMatchObject({ status: 409 });
    await expect(api.filesystem.uploadFile(rootId, { ...upload, name: '..' })).rejects.toBeInstanceOf(z.ZodError);
  });

  test('validates seed nodes and configured policy', (): void => {
    expect(() => new InMemoryFilesApi(rootId, [{ ...filesystemFixture[0], revision: 0 }])).toThrow(z.ZodError);
    expect(() => new InMemoryFilesApi(rootId, filesystemFixture, { max_bytes: 0 })).toThrow(z.ZodError);
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

  test.each([0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1, Infinity, NaN, '10', null])('rejects invalid upload limit %j', (max_bytes): void => {
    expect(uploadPolicySchema.safeParse({ max_bytes }).success).toBe(false);
  });

  test('accepts only a strict positive safe-integer policy', (): void => {
    expect(uploadPolicySchema.parse({ max_bytes: Number.MAX_SAFE_INTEGER })).toEqual({ max_bytes: Number.MAX_SAFE_INTEGER });
    expect(uploadPolicySchema.safeParse({ max_bytes: 10, extra: true }).success).toBe(false);
    expect(uploadPolicySchema.safeParse({}).success).toBe(false);
  });

  test.each(['', ' ', '.', '..', 'a/b', 'a\\b', 'a\u0000b'])('rejects invalid upload name %j', (name): void => {
    expect(fileNameSchema.safeParse(name).success).toBe(false);
    expect(fileUploadSchema.safeParse({ file: new File([], 'original'), name }).success).toBe(false);
  });

  test('requires a real file and explicit name without extra metadata', (): void => {
    const file = new File([], 'empty');
    expect(fileUploadSchema.parse({ file, name: 'chosen' })).toEqual({ file, name: 'chosen' });
    expect(fileUploadSchema.safeParse({ file }).success).toBe(false);
    expect(fileUploadSchema.safeParse({ file: new Blob([]), name: 'chosen' }).success).toBe(false);
    expect(fileUploadSchema.safeParse({ file: { name: 'fake', size: 0 }, name: 'chosen' }).success).toBe(false);
    expect(fileUploadSchema.safeParse({ file, name: 'chosen', metadata: {} }).success).toBe(false);
  });

  test('validates safely when File is unavailable during SSR', (): void => {
    vi.stubGlobal('File', undefined);
    try {
      expect(fileUploadSchema.safeParse({ file: {}, name: 'chosen' }).success).toBe(false);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  test('rejects null outbound metadata and malformed list envelopes', (): void => {
    expect(createFolderSchema.safeParse({ ...input, metadata: { content_type: null, attributes: {} } }).success).toBe(false);
    expect(childrenSchema.safeParse({ nodes: [null] }).success).toBe(false);
    expect(childrenSchema.safeParse([]).success).toBe(false);
  });
});

describe('filesystem upload HTTP boundary', () => {
  test('gets validated policy with the cancellation signal', async (): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ max_bytes: 10 }));
    const api: FilesApi = new HttpFilesApi(browserTransport({ fetch: request, configuration }));
    const signal = new AbortController().signal;
    expect(await api.filesystem.getUploadPolicy(rootId, signal)).toEqual({ max_bytes: 10 });
    expect(request).toHaveBeenCalledWith('/api/me/filesystem/nodes/' + rootId + '/upload-policy', expect.objectContaining({ method: 'GET', signal }));
  });

  test('uploads only file and name with the original filename, auth and browser-owned content type', async (): Promise<void> => {
    const created = filesystemNode({ id: fileId, parent_id: rootId, name: 'Chosen.txt', kind: 'file' });
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json(created, { status: 201 }));
    const api: FilesApi = new HttpFilesApi(browserTransport({ fetch: request, configuration, bearerToken: () => 'test-token' }));
    const file = new File(['hello'], 'Original.txt', { type: 'text/plain' });
    expect(await api.filesystem.uploadFile(rootId, { file, name: 'Chosen.txt' })).toEqual(created);
    const [url, init] = request.mock.calls[0];
    expect(url).toBe('/api/me/filesystem/nodes/' + rootId + '/files');
    expect(init).toMatchObject({ method: 'POST', credentials: 'same-origin' });
    const headers = new Headers(init?.headers);
    expect(headers.get('content-type')).toBeNull();
    expect(headers.get('authorization')).toBe('Bearer test-token');
    expect(headers.get('X-Umbod-Web-Request')).toBe('1');
    expect(init?.body).toBeInstanceOf(FormData);
    const form = init?.body as FormData;
    expect(Array.from(form.keys())).toEqual(['file', 'name']);
    expect(form.get('name')).toBe('Chosen.txt');
    const sent = form.get('file') as File;
    expect(sent.name).toBe('Original.txt');
    expect(sent.type).toBe('text/plain');
    expect(sent.size).toBe(file.size);
    expect(request).toHaveBeenCalledTimes(1);
  });

  test.each([
    { file: {}, name: 'valid' },
    { file: new File([], 'original'), name: '..' },
    { file: new File([], 'original') },
    { file: new File([], 'original'), name: 'valid', metadata: {} }
  ])('rejects the entire upload before form construction and network access', async (upload): Promise<void> => {
    const request = vi.fn<typeof fetch>();
    const api: FilesApi = new HttpFilesApi(browserTransport({ fetch: request, configuration }));
    const formConstructor = vi.fn();
    vi.stubGlobal('FormData', formConstructor);
    try {
      await expect(api.filesystem.uploadFile(rootId, upload as FileUpload)).rejects.toMatchObject({ direction: 'outbound' });
      expect(formConstructor).not.toHaveBeenCalled();
      expect(request).not.toHaveBeenCalled();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  test('validates both policy and upload responses', async (): Promise<void> => {
    const request = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({ max_bytes: 0 }))
      .mockResolvedValueOnce(Response.json({ invalid: true }));
    const api: FilesApi = new HttpFilesApi(browserTransport({ fetch: request, configuration }));
    await expect(api.filesystem.getUploadPolicy(rootId)).rejects.toMatchObject({ direction: 'inbound' });
    await expect(api.filesystem.uploadFile(rootId, { file: new File([], 'original'), name: 'chosen' })).rejects.toMatchObject({ direction: 'inbound' });
    expect(request).toHaveBeenCalledTimes(2);
  });

  test.each([401, 403, 404, 409, 413, 500])('preserves upload HTTP %s without replay', async (status): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ detail: 'rejected' }, { status }));
    const api: FilesApi = new HttpFilesApi(browserTransport({ fetch: request, configuration }));
    const result = api.filesystem.uploadFile(rootId, { file: new File([], 'original'), name: 'chosen' });
    if (status === 401) await expect(result).rejects.toBeInstanceOf(AuthenticationRequiredError);
    else await expect(result).rejects.toMatchObject({ status });
    expect(request).toHaveBeenCalledTimes(1);
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
