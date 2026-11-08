import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, HttpError, NetworkError, SchemaValidationError, type Transport, type TransportRequest } from '$lib/admin/infrastructure/transport';
import type { FilesApi } from './api';
import { browseResultSchema, type BrowseResult } from './domain/schemas';
import { deferred, fileId, filesystemFixture, filesystemNode, folderId, rootId } from './fixtures.test-support';
import { FilesystemRoute } from './infrastructure/filesystem-route';
import { InMemoryFilesApi } from './infrastructure/in-memory-api.test-support';
import { FilesState } from './state/files-state.svelte';
import { NewFolderState } from './state/new-folder-state.svelte';
import { UploadState } from './state/upload-state.svelte';

class RecordingTransport implements Transport {
  readonly requests: TransportRequest<unknown>[] = [];

  constructor(private readonly respond: (request: TransportRequest<unknown>) => Promise<unknown>) {}

  request = async <TOut>(request: TransportRequest<TOut>): Promise<TOut> => {
    this.requests.push(request);
    request.signal?.throwIfAborted();
    const response = await this.respond(request);
    if (!request.outputSchema) return undefined as TOut;
    const parsed = request.outputSchema.safeParse(response);
    if (!parsed.success) throw new SchemaValidationError('inbound', parsed.error.issues);
    return parsed.data;
  };
}

async function mixedResponse(): Promise<BrowseResult> {
  const memory = new InMemoryFilesApi(rootId, [
    ...filesystemFixture,
    filesystemNode({ id: '00000000-0000-4000-8000-000000000004', parent_id: folderId, name: 'Design' })
  ]);
  const result = await memory.filesystem.browse(folderId);
  return { ...result, capabilities: result.capabilities.map((capability) => ({ ...capability, share: true })) };
}

function fixture(respond: (request: TransportRequest<unknown>) => Promise<unknown>): { files: FilesState; api: FilesApi; transport: RecordingTransport } {
  const transport = new RecordingTransport(async (request) => request.path === '/me/filesystem/home' ? filesystemFixture[0] : respond(request));
  const unexpected = async (): Promise<never> => { throw new Error('Unexpected sharing probe'); };
  const api: FilesApi = {
    filesystem: new FilesystemRoute(transport, { transfer: unexpected }),
    sharing: { inspectAccess: vi.fn(unexpected), replaceAccess: vi.fn(unexpected), searchRecipients: vi.fn(unexpected) }
  };
  return { files: new FilesState(api), api, transport };
}

describe('coherent filesystem browse', (): void => {
  test('home resolution uses the caller-only POST and validates the returned node', async (): Promise<void> => {
    const home = filesystemNode({ id: folderId, parent_id: rootId, name: 'Home-opaque' });
    const transport = new RecordingTransport(async () => home);
    const route = new FilesystemRoute(transport, { transfer: async (): Promise<void> => {} });
    const signal = new AbortController().signal;
    expect(await route.getHome(signal)).toEqual(home);
    expect(transport.requests.map(({ method, path, signal: requestSignal }) => ({ method, path, signal: requestSignal }))).toEqual([
      { method: 'POST', path: '/me/filesystem/home', signal }
    ]);
    const invalid = new FilesystemRoute(new RecordingTransport(async () => ({ id: 'invalid' })), { transfer: async (): Promise<void> => {} });
    await expect(invalid.getHome()).rejects.toBeInstanceOf(SchemaValidationError);
  });

  test('home resolution and one GET initialize a directory without eligibility probes', async (): Promise<void> => {
    const response = await mixedResponse();
    const { files, api, transport } = fixture(async () => response);
    await files.load(folderId);
    expect(files.phase).toBe('ready');
    expect(files.children).toEqual(response.entries);
    expect(files.children.map((node) => node.kind)).toEqual(['file', 'directory']);
    expect(files.navigation.path).toEqual(response.breadcrumbs);
    expect(files.update.canRename).toBe(true);
    expect(files.update.canMove).toBe(true);
    expect(files.description.available).toBe(true);
    expect(files.sharing.available(folderId)).toBe(true);
    expect(files.uploadAvailability).toBe('allowed');
    expect(files.createDirectoryAllowed).toBe(true);
    for (const node of files.children) {
      expect(files.rowEditing.controllers.get(node.id)?.update.canRename).toBe(true);
      expect(files.rowEditing.controllers.get(node.id)?.update.canMove).toBe(true);
      expect(files.rowEditing.controllers.get(node.id)?.description.available).toBe(true);
      expect(files.sharing.available(node.id)).toBe(true);
    }
    expect(files.rowDeletion.controllers.get(fileId)?.available).toBe(true);
    expect(transport.requests.map(({ method, path }) => ({ method, path }))).toEqual([
      { method: 'POST', path: '/me/filesystem/home' },
      { method: 'GET', path: '/me/filesystem/browse?node_id=' + folderId }
    ]);
    expect(api.sharing.inspectAccess).not.toHaveBeenCalled();
    files.dispose();
  });

  test('accepted authoritative row and current updates reuse seeded eligibility without renewed probes', async (): Promise<void> => {
    const response = await mixedResponse();
    const { files, transport, api } = fixture(async (request) => {
      if (request.method === 'GET') return response;
      const original = request.path.endsWith(fileId) ? response.entries[0] : response.node;
      return { ...original, name: 'Canonical', revision: original.revision + 1 };
    });
    await files.load(folderId);
    const row = files.rowEditing.controllers.get(fileId)!;
    row.update.showRename();
    row.update.changeName('Draft');
    await row.update.submit();
    expect(files.children[0]).toMatchObject({ name: 'Canonical', revision: 2 });
    expect(row.description.available).toBe(true);
    expect(files.rowDeletion.controllers.get(fileId)?.available).toBe(true);
    files.update.showRename();
    files.update.changeName('Folder draft');
    await files.update.submit();
    expect(files.node?.name).toBe('Canonical');
    expect(files.navigation.path?.items.at(-1)?.name).toBe('Canonical');
    expect(transport.requests.map(({ method }) => method)).toEqual(['POST', 'GET', 'PATCH', 'PATCH']);
    expect(api.sharing.inspectAccess).not.toHaveBeenCalled();
    files.dispose();
  });

  test('personal root uses its resolved UUID and file inspection uses an empty listing', async (): Promise<void> => {
    const memory = new InMemoryFilesApi(rootId, filesystemFixture);
    const { api, transport, files } = fixture(async (request) => memory.filesystem.browse(request.path.endsWith(fileId) ? fileId : rootId));
    await files.load(null);
    expect(files.node?.id).toBe(rootId);
    expect(transport.requests[0].path).toBe('/me/filesystem/home');
    expect(transport.requests[1].path).toBe('/me/filesystem/browse?node_id=' + rootId);
    await files.load(fileId);
    expect(files.children).toEqual([]);
    expect(files.deletion.available).toBe(true);
    expect(files.uploadAvailability).toBe('hidden');
    expect(transport.requests).toHaveLength(3);
    await expect(api.filesystem.browse('invalid')).rejects.toThrow();
    expect(transport.requests).toHaveLength(3);
    files.dispose();
  });

  test('denied advisory capabilities keep actions closed and never dispatch mutations', async (): Promise<void> => {
    const response = await mixedResponse();
    const denied = response.capabilities.map(({ node_id }) => ({ node_id, rename: false, move: false, edit_description: false, delete: false, share: false, upload: false, create_directory: false }));
    const { files, api, transport } = fixture(async () => ({ ...response, capabilities: denied }));
    await files.load(folderId);
    const folder = new NewFolderState(api, files);
    const upload = new UploadState(api, files);
    folder.show();
    upload.show();
    files.update.showRename();
    files.update.showMove();
    files.description.show();
    const row = files.rowEditing.controllers.get(fileId)!;
    row.update.showRename();
    row.description.show();
    files.rowDeletion.controllers.get(fileId)?.show();
    await folder.submit();
    await upload.submit();
    await row.update.submit();
    await row.description.save();
    await files.rowDeletion.confirm(fileId);
    expect(folder.open).toBe(false);
    expect(upload.open).toBe(false);
    expect(files.update.open).toBe(false);
    expect(files.description.open).toBe(false);
    expect(row.update.open).toBe(false);
    expect(row.description.open).toBe(false);
    expect(files.sharing.available(fileId)).toBe(false);
    expect(transport.requests).toHaveLength(2);
    folder.dispose();
    upload.dispose();
    files.dispose();
  });

  test.each([
    (result: BrowseResult): unknown => ({ ...result, truncated: true }),
    (result: BrowseResult): unknown => ({ ...result, capabilities: result.capabilities.slice(1) }),
    (result: BrowseResult): unknown => ({ ...result, capabilities: [...result.capabilities, result.capabilities[0]] }),
    (result: BrowseResult): unknown => ({ ...result, entries: [...result.entries, result.entries[0]] }),
    (result: BrowseResult): unknown => ({ ...result, entries: [{ ...result.entries[0], parent_id: rootId }] }),
    (result: BrowseResult): unknown => ({ ...result, breadcrumbs: { ...result.breadcrumbs, items: result.breadcrumbs.items.slice(0, 1) } }),
    (result: BrowseResult): unknown => ({ ...result, capabilities: result.capabilities.map((capability) => ({ ...capability, rename: 'yes' })) }),
    (result: BrowseResult): unknown => ({ ...result, node: { ...result.node, kind: 'file' } })
  ])('rejects malformed or cross-result-inconsistent responses and fails closed', async (corrupt): Promise<void> => {
    const response = await mixedResponse();
    const malformed = corrupt(response);
    expect(browseResultSchema.safeParse(malformed).success).toBe(false);
    const { files, api } = fixture(async () => malformed);
    await expect(api.filesystem.browse(folderId)).rejects.toBeInstanceOf(SchemaValidationError);
    await files.load(folderId);
    expect(files.phase).toBe('error');
    expect(files.node).toBeUndefined();
    expect(files.children).toEqual([]);
    expect(files.navigation.path).toBeUndefined();
    expect(files.update.canRename).toBe(false);
    expect(files.uploadAvailability).toBe('hidden');
    expect(files.createDirectoryAllowed).toBe(false);
    files.dispose();
  });

  test.each([
    [new HttpError(403, 'Forbidden', {}), 'denied'],
    [new HttpError(404, 'Missing', {}), 'missing'],
    [new AuthenticationRequiredError(), 'sign-in'],
    [new NetworkError('offline'), 'error']
  ] as const)('read failure %s clears previously authorized content and retry restores it', async (error, phase): Promise<void> => {
    const response = await mixedResponse();
    let fail = false;
    const { files } = fixture(async () => { if (fail) throw error; return response; });
    await files.load(folderId);
    fail = true;
    await files.reload();
    expect(files.phase).toBe(phase);
    expect(files.node).toBeUndefined();
    expect(files.children).toEqual([]);
    expect(files.sharing.available(folderId)).toBe(false);
    expect(files.update.canRename).toBe(false);
    expect(files.createDirectoryAllowed).toBe(false);
    fail = false;
    await files.reload();
    expect(files.phase).toBe('ready');
    files.dispose();
  });

  test.each(['navigate', 'dispose', 'reload'])('late browse results are fenced after %s and never expose a partial heading', async (action): Promise<void> => {
    const memory = new InMemoryFilesApi(rootId, filesystemFixture);
    const response = await memory.filesystem.browse(folderId);
    const pending = deferred<BrowseResult>();
    let first = true;
    const { files, transport } = fixture(async () => {
      if (first) { first = false; return pending.promise; }
      return action === 'navigate' ? memory.filesystem.browse(null) : response;
    });
    const loading = files.load(folderId);
    await vi.waitFor(() => expect(transport.requests).toHaveLength(2));
    expect(files.node).toBeUndefined();
    expect(files.navigation.path).toBeUndefined();
    expect(files.children).toEqual([]);
    if (action === 'dispose') files.dispose();
    else if (action === 'navigate') await files.load(null);
    else await files.reload();
    expect(transport.requests[1].signal?.aborted).toBe(true);
    pending.resolve(response);
    await loading;
    expect(files.node?.id).toBe(action === 'dispose' ? undefined : action === 'navigate' ? rootId : folderId);
    files.dispose();
  });

  test('a concurrent authoritative move refreshes stale browse ancestry without losing the newer revision', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    const files = new FilesState(api);
    await files.load(fileId);
    const staleResponse = await api.filesystem.browse(fileId);
    const commit = deferred<void>();
    const updateNode = api.filesystem.updateNode;
    const update = vi.spyOn(api.filesystem, 'updateNode').mockImplementation(async (id, revision, input) => {
      await commit.promise;
      return updateNode(id, revision, input);
    });
    const moving = files.update.moveTo(filesystemFixture[0]);
    await vi.waitFor(() => expect(update).toHaveBeenCalledOnce());
    const pending = deferred<BrowseResult>();
    vi.spyOn(api.filesystem, 'browse').mockReturnValueOnce(pending.promise);
    const pathRead = vi.spyOn(api.filesystem, 'getBreadcrumbs');
    const loading = files.load(fileId);
    commit.resolve();
    await moving;
    pending.resolve(staleResponse);
    await loading;
    await vi.waitFor(() => expect(files.navigation.parent?.id).toBe(rootId));
    expect(files.node).toMatchObject({ id: fileId, parent_id: rootId, revision: 2 });
    expect(files.navigation.path?.items.map((item) => item.id)).toEqual([rootId, fileId]);
    expect(pathRead).toHaveBeenCalledExactlyOnceWith(fileId, expect.any(AbortSignal));
    files.dispose();
  });

  test('rejects a coherent response for a different target', async (): Promise<void> => {
    const response = await mixedResponse();
    const { files, api } = fixture(async () => response);
    await expect(api.filesystem.browse(rootId)).rejects.toBeInstanceOf(SchemaValidationError);
    await files.load(rootId);
    expect(files.phase).toBe('error');
    expect(files.node).toBeUndefined();
    files.dispose();
  });
});
