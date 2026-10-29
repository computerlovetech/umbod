import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, HttpError, NetworkError } from '$lib/admin/infrastructure/transport';
import { WorkspaceAccessState } from '$lib/workspace/workspace-access-state.svelte';
import type { FilesApi } from '../api';
import type { NodeSummary } from '../domain/schemas';
import { deferred, fileId, filesystemFixture, filesystemNode, folderId, rootId } from '../fixtures.test-support';
import { InMemoryFilesApi } from '../infrastructure/in-memory-api';
import { FilesState } from './files-state.svelte';
import { NewFolderState } from './new-folder-state.svelte';

function fixture(): { api: FilesApi; files: FilesState; form: NewFolderState } {
  const api: FilesApi = new InMemoryFilesApi(rootId, filesystemFixture);
  const files = new FilesState(api);
  return { api, files, form: new NewFolderState(api, files) };
}

describe('files reads and authoritative navigation', () => {
  test('root is independent of denied or pending administration lookup', async (): Promise<void> => {
    const { files } = fixture();
    const access = new WorkspaceAccessState({ currentUser: async () => { throw new HttpError(403, 'Forbidden', {}); } });
    await Promise.all([files.load(null), access.load()]);
    expect(files.phase).toBe('ready');
    expect(files.node?.id).toBe(rootId);
    expect(access.adminAccess).toBe('denied');
    const pending = new WorkspaceAccessState({ currentUser: () => new Promise(() => {}) });
    void pending.load();
    await files.reload();
    expect(files.phase).toBe('ready');
    pending.dispose();
  });

  test('deep file links retrieve the authoritative path without listing ancestors', async (): Promise<void> => {
    const { api, files } = fixture();
    const root = vi.spyOn(api.filesystem, 'getRoot');
    const getNode = vi.spyOn(api.filesystem, 'getNode');
    const children = vi.spyOn(api.filesystem, 'listChildren');
    await files.load(fileId);
    expect(files.node?.name).toBe('Notes.txt');
    expect(files.children).toEqual([]);
    expect(files.navigation.path?.items.map((item) => item.id)).toEqual([rootId, folderId, fileId]);
    expect(root).not.toHaveBeenCalled();
    expect(getNode.mock.calls).toEqual([[fileId, expect.any(AbortSignal)]]);
    expect(children).not.toHaveBeenCalled();
  });

  test('directory deep links list children and retrieve authoritative paths without a root read', async (): Promise<void> => {
    const { api, files } = fixture();
    const root = vi.spyOn(api.filesystem, 'getRoot');
    await files.load(folderId);
    expect(files.children.map((node) => node.id)).toEqual([fileId]);
    expect(files.navigation.path?.items.map((item) => item.id)).toEqual([rootId, folderId]);
    expect(root).not.toHaveBeenCalled();
  });

  test('back and forward URL selections reload authoritative paths and discard folder drafts', async (): Promise<void> => {
    const { files, form } = fixture();
    await files.load(null);
    form.show();
    form.changeName('discard on navigation');
    form.navigate();
    await files.load(folderId);
    await files.load(fileId);
    expect(files.navigation.path?.items.map((item) => item.id)).toEqual([rootId, folderId, fileId]);
    form.navigate();
    await files.load(folderId);
    expect(files.node?.id).toBe(folderId);
    expect(form.name).toBe('');
    await files.load(fileId);
    expect(files.node?.id).toBe(fileId);
    await files.load(null);
    expect(files.navigation.path?.items.map((item) => item.id)).toEqual([rootId]);
  });

  test.each([
    [new HttpError(403, 'Forbidden', {}), 'denied'],
    [new HttpError(404, 'Missing', {}), 'missing'],
    [new AuthenticationRequiredError(), 'sign-in'],
    [new NetworkError('offline'), 'error']
  ])('distinguishes failed reads and allows explicit retry', async (error, phase): Promise<void> => {
    const { api, files } = fixture();
    const read = vi.spyOn(api.filesystem, 'getRoot').mockRejectedValueOnce(error);
    await files.load(null);
    expect(files.phase).toBe(phase);
    expect(files.node).toBeUndefined();
    expect(files.creationTarget()).toBeUndefined();
    expect(read).toHaveBeenCalledTimes(1);
    await files.reload();
    expect(files.phase).toBe('ready');
  });

  test('malformed URL IDs make no request', async (): Promise<void> => {
    const { api, files } = fixture();
    const read = vi.spyOn(api.filesystem, 'getNode');
    await files.load('not-a-uuid');
    expect(files.phase).toBe('error');
    expect(read).not.toHaveBeenCalled();
  });

  test('late node and children results cannot replace the current location', async (): Promise<void> => {
    const { api, files } = fixture();
    const stale = deferred<NodeSummary[]>();
    vi.spyOn(api.filesystem, 'listChildren').mockImplementationOnce(() => stale.promise);
    const first = files.load(null);
    await vi.waitFor(() => expect(api.filesystem.listChildren).toHaveBeenCalled());
    await files.load(fileId);
    stale.resolve([filesystemFixture[1]]);
    await first;
    expect(files.node?.id).toBe(fileId);
    expect(files.children).toEqual([]);
    const lateNode = deferred<NodeSummary>();
    vi.spyOn(api.filesystem, 'getRoot').mockImplementationOnce(() => lateNode.promise);
    const second = files.load(null);
    await files.load(folderId);
    lateNode.resolve(filesystemFixture[0]);
    await second;
    expect(files.node?.id).toBe(folderId);
  });

  test('disposal aborts transport and ignores late results', async (): Promise<void> => {
    const { api, files } = fixture();
    const late = deferred<NodeSummary>();
    const read = vi.spyOn(api.filesystem, 'getRoot').mockImplementationOnce(() => late.promise);
    const pending = files.load(null);
    const signal = read.mock.calls[0][0];
    files.dispose();
    expect(signal?.aborted).toBe(true);
    late.resolve(filesystemFixture[0]);
    await pending;
    expect(files.node).toBeUndefined();
  });
});

describe('server-authoritative folder creation', () => {
  test('requires a loaded directory and appends a confirmed folder only once', async (): Promise<void> => {
    const { api, files, form } = fixture();
    const create = vi.spyOn(api.filesystem, 'createFolder');
    form.show();
    expect(form.open).toBe(false);
    await files.load(null);
    form.show();
    form.changeName('Design');
    await form.submit();
    expect(form.open).toBe(false);
    expect(files.children.filter((node) => node.name === 'Design')).toHaveLength(1);
    expect(create).toHaveBeenCalledWith(rootId, { name: 'Design', metadata: { content_type: {}, attributes: {} } });
    await files.load(fileId);
    form.show();
    expect(form.open).toBe(false);
  });

  test.each([403, 409])('preserves input on %s and never retries automatically', async (status): Promise<void> => {
    const { api, files, form } = fixture();
    const create = vi.spyOn(api.filesystem, 'createFolder').mockRejectedValueOnce(new HttpError(status, 'Rejected', {}));
    await files.load(null);
    form.show();
    form.changeName('Keep this name');
    await form.submit();
    expect(form.name).toBe('Keep this name');
    expect(form.open).toBe(true);
    expect(form.error).toMatch(status === 403 ? /can't create/ : /already exists/);
    expect(form.uncertain).toBe(false);
    expect(create).toHaveBeenCalledTimes(1);
    await form.submit();
    expect(create).toHaveBeenCalledTimes(2);
    expect(form.open).toBe(false);
  });

  test('unknown writes remain blocked across navigation until explicit successful reload', async (): Promise<void> => {
    const { api, files, form } = fixture();
    const create = vi.spyOn(api.filesystem, 'createFolder').mockRejectedValueOnce(new NetworkError('lost response'));
    await files.load(null);
    form.show();
    form.changeName('Uncertain');
    await form.submit();
    expect(form.name).toBe('Uncertain');
    expect(form.uncertain).toBe(true);
    await form.submit();
    expect(create).toHaveBeenCalledTimes(1);
    form.navigate();
    await files.load(folderId);
    form.navigate();
    await files.load(null);
    form.show();
    expect(form.uncertain).toBe(true);
    await form.submit();
    expect(create).toHaveBeenCalledTimes(1);
    await form.reload();
    form.show();
    expect(form.uncertain).toBe(false);
    form.changeName('Different folder');
    await form.submit();
    expect(create).toHaveBeenCalledTimes(2);
  });

  test('pending creation locks input and duplicate submits, and Escape cannot hide the write', async (): Promise<void> => {
    const { api, files, form } = fixture();
    const result = deferred<NodeSummary>();
    const create = vi.spyOn(api.filesystem, 'createFolder').mockImplementationOnce(() => result.promise);
    await files.load(null);
    form.show();
    form.changeName('Waiting');
    const write = form.submit();
    form.changeName('Ignored');
    form.cancel();
    await form.submit();
    expect(form.open).toBe(true);
    expect(form.name).toBe('Waiting');
    expect(form.pending).toBe(true);
    expect(create).toHaveBeenCalledTimes(1);
    result.resolve(filesystemNode({ id: fileId, parent_id: rootId, name: 'Waiting' }));
    await write;
    expect(form.pending).toBe(false);
  });

  test('late creation does not append to a different directory or clear its draft', async (): Promise<void> => {
    const { api, files, form } = fixture();
    const result = deferred<NodeSummary>();
    vi.spyOn(api.filesystem, 'createFolder').mockImplementationOnce(() => result.promise);
    await files.load(null);
    form.show();
    form.changeName('Old');
    const write = form.submit();
    form.navigate();
    await files.load(folderId);
    form.show();
    form.changeName('New draft');
    result.resolve(filesystemNode({ id: fileId, parent_id: rootId, name: 'Old' }));
    await write;
    expect(files.children.map((node) => node.name)).toEqual(['Notes.txt']);
    expect(form.name).toBe('New draft');
    expect(form.open).toBe(true);
  });

  test.each([null, folderId])('confirmed creation refetches parent %s after navigating away and back to a completed listing', async (selection): Promise<void> => {
    const { api, files, form } = fixture();
    const parentId = selection ?? rootId;
    const commit = deferred<void>();
    const createFolder = api.filesystem.createFolder;
    const create = vi.spyOn(api.filesystem, 'createFolder').mockImplementation(async (parent, input) => {
      await commit.promise;
      return createFolder(parent, input);
    });
    const list = vi.spyOn(api.filesystem, 'listChildren');
    await files.load(selection);
    form.show();
    form.changeName('Confirmed after return');
    const write = form.submit();
    form.navigate();
    await files.load(selection === null ? folderId : null);
    form.navigate();
    await files.load(selection);
    expect(files.children.some((node) => node.name === 'Confirmed after return')).toBe(false);
    const previousReads = list.mock.calls.filter(([, signal]) => signal).length;
    commit.resolve();
    await write;
    expect(files.phase).toBe('ready');
    expect(files.node?.id).toBe(parentId);
    expect(files.children.filter((node) => node.name === 'Confirmed after return')).toHaveLength(1);
    expect(list.mock.calls.filter(([, signal]) => signal)).toHaveLength(previousReads + 1);
    expect(list).toHaveBeenLastCalledWith(parentId, expect.any(AbortSignal));
    expect(create).toHaveBeenCalledTimes(1);
    expect(form.uncertain).toBe(false);
  });

  test.each([null, folderId])('confirmed creation invalidates a pending stale parent %s listing before authorized refetch', async (selection): Promise<void> => {
    const { api, files, form } = fixture();
    const parentId = selection ?? rootId;
    const commit = deferred<void>();
    const createFolder = api.filesystem.createFolder;
    const create = vi.spyOn(api.filesystem, 'createFolder').mockImplementation(async (parent, input) => {
      await commit.promise;
      return createFolder(parent, input);
    });
    const list = vi.spyOn(api.filesystem, 'listChildren');
    await files.load(selection);
    const snapshot = [...files.children];
    form.show();
    form.changeName('Committed while loading');
    const write = form.submit();
    form.navigate();
    await files.load(selection === null ? folderId : null);
    const stale = deferred<NodeSummary[]>();
    list.mockImplementationOnce(() => stale.promise);
    const previousReads = list.mock.calls.filter(([, signal]) => signal).length;
    form.navigate();
    const returning = files.load(selection);
    await vi.waitFor(() => expect(list.mock.calls.filter(([, signal]) => signal)).toHaveLength(previousReads + 1));
    const staleSignal = list.mock.calls.filter(([, signal]) => signal)[previousReads][1];
    expect(files.phase).toBe('loading');
    commit.resolve();
    await write;
    expect(staleSignal?.aborted).toBe(true);
    expect(files.node?.id).toBe(parentId);
    expect(files.children.filter((node) => node.name === 'Committed while loading')).toHaveLength(1);
    expect(list.mock.calls.filter(([, signal]) => signal)).toHaveLength(previousReads + 2);
    stale.resolve(snapshot);
    await returning;
    expect(files.phase).toBe('ready');
    expect(files.children.filter((node) => node.name === 'Committed while loading')).toHaveLength(1);
    expect(create).toHaveBeenCalledTimes(1);
  });

  test('confirmed creation leaves a different directory loading without refetching or injecting its result', async (): Promise<void> => {
    const { api, files, form } = fixture();
    const result = deferred<NodeSummary>();
    const create = vi.spyOn(api.filesystem, 'createFolder').mockImplementationOnce(() => result.promise);
    const list = vi.spyOn(api.filesystem, 'listChildren');
    await files.load(null);
    form.show();
    form.changeName('Root child');
    const write = form.submit();
    form.navigate();
    const stale = deferred<NodeSummary[]>();
    list.mockImplementationOnce(() => stale.promise);
    const loadingOther = files.load(folderId);
    await vi.waitFor(() => expect(list).toHaveBeenCalledTimes(2));
    const signal = list.mock.calls[1][1];
    result.resolve(filesystemNode({ id: fileId, parent_id: rootId, name: 'Root child' }));
    await write;
    expect(files.phase).toBe('loading');
    expect(signal?.aborted).toBe(false);
    expect(list).toHaveBeenCalledTimes(2);
    stale.resolve([filesystemFixture[2]]);
    await loadingOther;
    expect(files.node?.id).toBe(folderId);
    expect(files.children.map((node) => node.name)).toEqual(['Notes.txt']);
    expect(create).toHaveBeenCalledTimes(1);
  });

  test('confirmed creation never bypasses denied reconciliation or marks the confirmed write uncertain', async (): Promise<void> => {
    const { api, files, form } = fixture();
    const commit = deferred<void>();
    const createFolder = api.filesystem.createFolder;
    const create = vi.spyOn(api.filesystem, 'createFolder').mockImplementation(async (parent, input) => {
      await commit.promise;
      return createFolder(parent, input);
    });
    await files.load(null);
    form.show();
    form.changeName('Committed');
    const write = form.submit();
    form.navigate();
    await files.load(folderId);
    form.navigate();
    await files.load(null);
    vi.spyOn(api.filesystem, 'getRoot').mockRejectedValueOnce(new HttpError(403, 'Forbidden', {}));
    commit.resolve();
    await write;
    expect(files.phase).toBe('denied');
    expect(files.children).toEqual([]);
    expect(form.uncertain).toBe(false);
    expect(create).toHaveBeenCalledTimes(1);
  });

  test('invalid names and cancellation never send a write', async (): Promise<void> => {
    const { api, files, form } = fixture();
    const create = vi.spyOn(api.filesystem, 'createFolder');
    await files.load(null);
    form.show();
    form.changeName('../bad');
    await form.submit();
    expect(form.error).toMatch(/folder name/);
    form.cancel();
    expect(form.open).toBe(false);
    expect(create).not.toHaveBeenCalled();
  });
});
