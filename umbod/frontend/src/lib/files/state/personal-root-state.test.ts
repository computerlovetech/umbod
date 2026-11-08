import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, HttpError, NetworkError } from '$lib/admin/infrastructure/transport';
import type { NodeSummary } from '../domain/schemas';
import { deferred, fileId, filesystemNode, folderId, rootId } from '../fixtures.test-support';
import { InMemoryFilesApi } from '../infrastructure/in-memory-api.test-support';
import { FilesState } from './files-state.svelte';
import { NewFolderState } from './new-folder-state.svelte';

function fixture(rootVisible: boolean = true): { api: InMemoryFilesApi; files: FilesState; home: NodeSummary } {
  const home = filesystemNode({ id: folderId, parent_id: rootId, name: 'Home-opaque-identifier' });
  const child = filesystemNode({ id: fileId, parent_id: folderId, name: 'Projects' });
  const api = new InMemoryFilesApi(rootId, [filesystemNode(), home, child], undefined, undefined, (node) => rootVisible || node.id !== rootId);
  vi.spyOn(api.filesystem, 'getHome').mockImplementation((signal) => api.filesystem.getNode(folderId, signal));
  return { api, files: new FilesState(api), home };
}

describe('personal Files root', () => {
  test.each([true, false])('opens home contents without a wrapper or parent when shared root visibility is %s', async (rootVisible): Promise<void> => {
    const { api, files, home } = fixture(rootVisible);
    const browse = vi.spyOn(api.filesystem, 'browse');
    await files.load(null);
    expect(files.phase).toBe('ready');
    expect(files.node).toMatchObject({ id: home.id, name: home.name });
    expect(files.locationName).toBe('Files');
    expect(files.children.map((node) => node.name)).toEqual(['Projects']);
    expect(files.navigation.displayItems.map((item) => item.id)).toEqual([folderId]);
    expect(files.navigation.atRoot).toBe(true);
    expect(files.navigation.parent).toBeUndefined();
    expect(files.update.canRename).toBe(false);
    expect(files.update.canMove).toBe(false);
    expect(browse).toHaveBeenCalledExactlyOnceWith(folderId, expect.any(AbortSignal));
    files.dispose();
  });

  test('deep links and reload keep home as the navigation boundary while retaining authoritative ancestry', async (): Promise<void> => {
    const { api, files } = fixture();
    await files.load(fileId);
    expect(files.navigation.path?.items.map((item) => item.id)).toEqual([rootId, folderId, fileId]);
    expect(files.navigation.displayItems.map((item) => item.id)).toEqual([folderId, fileId]);
    expect(files.navigation.label(files.navigation.parent!)).toBe('Files');
    expect(files.navigation.href(files.navigation.parent!)).toBe('/files');
    await files.reload();
    expect(api.filesystem.getHome).toHaveBeenCalledTimes(1);
    expect(files.navigation.displayItems.map((item) => item.id)).toEqual([folderId, fileId]);
    files.dispose();
  });

  test('new folders are created inside home, not in the shared root', async (): Promise<void> => {
    const { api, files } = fixture();
    const form = new NewFolderState(api, files);
    await files.load(null);
    form.show();
    form.changeName('Plans');
    await form.submit();
    expect(files.children.find((node) => node.name === 'Plans')?.parent_id).toBe(folderId);
    expect((await api.filesystem.listChildren(rootId)).map((node) => node.id)).toEqual([folderId]);
    form.dispose();
    files.dispose();
  });

  test('renaming a home does not change its personal-root presentation', async (): Promise<void> => {
    const { api, files } = fixture();
    await api.filesystem.updateNode(folderId, 1, { name: 'Renamed home' });
    await files.load(folderId);
    expect(files.node?.name).toBe('Renamed home');
    expect(files.locationName).toBe('Files');
    expect(files.navigation.atRoot).toBe(true);
    files.dispose();
  });

  test('shared-root links retain their UUID destination instead of returning to home', async (): Promise<void> => {
    const { files } = fixture();
    await files.load(rootId);
    expect(files.locationName).toBe('Shared files');
    expect(files.navigation.href(files.navigation.displayItems[0])).toBe('/files?node=' + rootId);
    expect(files.atPersonalRoot).toBe(false);
    files.dispose();
  });

  test.each([
    [new AuthenticationRequiredError(), 'sign-in'],
    [new HttpError(403, 'Forbidden', {}), 'denied'],
    [new NetworkError('offline'), 'error']
  ])('home resolution failure does not fall back to the shared root: %s', async (error, phase): Promise<void> => {
    const { api, files } = fixture();
    vi.mocked(api.filesystem.getHome).mockRejectedValue(error);
    const browse = vi.spyOn(api.filesystem, 'browse');
    await files.load(null);
    expect(files.phase).toBe(phase);
    expect(files.node).toBeUndefined();
    expect(browse).not.toHaveBeenCalled();
    files.dispose();
  });

  test('home lookup failure does not block an explicit accessible node', async (): Promise<void> => {
    const { api, files } = fixture();
    vi.mocked(api.filesystem.getHome).mockRejectedValue(new NetworkError('offline'));
    await files.load(fileId);
    expect(files.phase).toBe('ready');
    expect(files.node?.id).toBe(fileId);
    files.dispose();
  });

  test.each(['navigate', 'dispose'] as const)('late home resolution cannot replace the location after %s', async (action): Promise<void> => {
    const { api, files, home } = fixture();
    const pending = deferred<NodeSummary>();
    vi.mocked(api.filesystem.getHome).mockReturnValueOnce(pending.promise);
    const loading = files.load(null);
    const signal = vi.mocked(api.filesystem.getHome).mock.calls[0][0];
    if (action === 'navigate') await files.load(fileId);
    else files.dispose();
    pending.resolve(home);
    await loading;
    expect(signal?.aborted).toBe(true);
    expect(files.node?.id).toBe(action === 'navigate' ? fileId : undefined);
    files.dispose();
  });
});
