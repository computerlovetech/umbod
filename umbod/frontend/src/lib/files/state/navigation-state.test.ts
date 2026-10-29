import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, HttpError, NetworkError } from '$lib/admin/infrastructure/transport';
import type { Breadcrumbs, NodeSummary } from '../domain/schemas';
import { deferred, fileId, filesystemFixture, filesystemNode, folderId, rootId } from '../fixtures.test-support';
import { InMemoryFilesApi } from '../infrastructure/in-memory-api';
import { FilesState } from './files-state.svelte';

const siblingId = '00000000-0000-4000-8000-000000000004';
const sibling = filesystemNode({ id: siblingId, parent_id: rootId, name: 'Design' });
const path: Breadcrumbs = { items: filesystemFixture.map(({ id, name, kind }) => ({ id, name, kind })), complete: true };

function fixture(): { api: InMemoryFilesApi; files: FilesState } {
  const api = new InMemoryFilesApi(rootId, [...filesystemFixture, sibling]);
  return { api, files: new FilesState(api) };
}

describe('authoritative file navigation', () => {
  test('direct deep links, reload and root selections never rely on visit history', async (): Promise<void> => {
    const { api, files } = fixture();
    const read = vi.spyOn(api.filesystem, 'getBreadcrumbs');
    await files.load(fileId);
    expect(files.navigation.path).toEqual(path);
    expect(files.navigation.parent?.id).toBe(folderId);
    expect(files.navigation.href(path.items[0])).toBe('/files');
    expect(files.navigation.label(path.items[0])).toBe('Files');
    await files.reload();
    expect(read).toHaveBeenCalledTimes(2);
    await files.load(folderId);
    expect(files.navigation.parent?.id).toBe(rootId);
    await files.load(null);
    expect(files.navigation.atRoot).toBe(true);
    expect(files.navigation.parent).toBeUndefined();
  });

  test('partial paths retain visible parents but never fabricate a root or parent for the first item', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture, undefined, undefined, (node) => node.id !== rootId);
    const files = new FilesState(api);
    await files.load(fileId);
    expect(files.navigation.path).toEqual({ items: path.items.slice(1), complete: false });
    expect(files.navigation.parent?.id).toBe(folderId);
    expect(files.navigation.href(path.items[1])).toContain(folderId);
    await files.load(folderId);
    expect(files.navigation.parent).toBeUndefined();
    expect(files.navigation.atRoot).toBe(false);
  });

  test('a stalled navigation read does not delay or erase a usable directory listing', async (): Promise<void> => {
    const { api, files } = fixture();
    const pending = deferred<Breadcrumbs>();
    vi.spyOn(api.filesystem, 'getBreadcrumbs').mockReturnValueOnce(pending.promise);
    await files.load(folderId);
    expect(files.phase).toBe('ready');
    expect(files.children.map((node) => node.id)).toEqual([fileId]);
    expect(files.navigation.phase).toBe('loading');
    pending.reject(new NetworkError('private failure'));
    await vi.waitFor(() => expect(files.navigation.phase).toBe('error'));
    expect(files.phase).toBe('ready');
    expect(files.children).toHaveLength(1);
    await files.navigation.reload();
    expect(files.navigation.phase).toBe('ready');
  });

  test('breadcrumbs can resolve while directory contents remain stalled', async (): Promise<void> => {
    const { api, files } = fixture();
    const pending = deferred<NodeSummary[]>();
    vi.spyOn(api.filesystem, 'listChildren').mockReturnValueOnce(pending.promise);
    const loading = files.load(folderId);
    await vi.waitFor(() => expect(files.navigation.phase).toBe('ready'));
    expect(files.phase).toBe('loading');
    pending.resolve([filesystemFixture[2]]);
    await loading;
    expect(files.phase).toBe('ready');
  });

  test.each([
    { ...path, items: path.items.slice(0, 2) },
    { ...path, items: [path.items[2]] },
    { ...path, items: path.items.slice(1) },
    { ...path, items: [{ ...path.items[0], name: 'Not the root' }, ...path.items.slice(1)] },
    { ...path, items: [...path.items.slice(0, 2), { ...path.items[2], kind: 'directory' }] },
    { ...path, items: [path.items[2], path.items[1], path.items[2]] }
  ])('rejects mismatched or corrupt path responses without affecting file details', async (response): Promise<void> => {
    const { api, files } = fixture();
    vi.spyOn(api.filesystem, 'getBreadcrumbs').mockResolvedValueOnce(response as Breadcrumbs);
    await files.load(fileId);
    expect(files.navigation.phase).toBe('error');
    expect(files.navigation.path).toBeUndefined();
    expect(files.navigation.atRoot).toBe(false);
    expect(files.navigation.label(path.items[2])).toBe('Notes.txt');
    expect(files.navigation.href(path.items[2])).toBe('/files?node=' + fileId);
    expect(files.phase).toBe('ready');
  });

  test.each([
    [new AuthenticationRequiredError(), 'sign-in'],
    [new HttpError(403, 'private', {}), 'denied'],
    [new Error('private'), 'error']
  ])('keeps navigation failure separate from content', async (error, phase): Promise<void> => {
    const { api, files } = fixture();
    vi.spyOn(api.filesystem, 'getBreadcrumbs').mockRejectedValueOnce(error);
    await files.load(folderId);
    expect(files.navigation.phase).toBe(phase);
    expect(files.phase).toBe('ready');
    expect(files.children).toHaveLength(1);
  });

  test.each(['navigate', 'dispose', 'retry'])('late navigation replies cannot survive %s', async (action): Promise<void> => {
    const { api, files } = fixture();
    const pending = deferred<Breadcrumbs>();
    const read = vi.spyOn(api.filesystem, 'getBreadcrumbs').mockReturnValueOnce(pending.promise);
    await files.load(fileId);
    const signal = read.mock.calls[0][1];
    if (action === 'navigate') await files.load(null);
    else if (action === 'dispose') files.dispose();
    else await files.navigation.reload();
    expect(signal?.aborted).toBe(true);
    pending.resolve({ items: [path.items[2]], complete: false });
    await Promise.resolve();
    expect(files.navigation.path).toEqual(action === 'dispose' ? undefined : action === 'navigate' ? { items: [path.items[0]], complete: true } : path);
  });
});

describe('known ancestor overflow', () => {
  const ancestors = Array.from({ length: 6 }, (_, index) => ({
    id: '00000000-0000-4000-8000-' + String(index + 10).padStart(12, '0'),
    name: 'Folder ' + index,
    kind: 'directory' as const
  }));
  const longPath: Breadcrumbs = { items: [path.items[0], ...ancestors, path.items[2]], complete: true };

  test.each([4, 5, 8])('collapses only middle ancestors for %s items without listing folders', async (length): Promise<void> => {
    const { api, files } = fixture();
    const items = [...longPath.items.slice(0, length - 1), path.items[2]];
    vi.spyOn(api.filesystem, 'getBreadcrumbs').mockResolvedValueOnce({ items, complete: true });
    const list = vi.spyOn(api.filesystem, 'listChildren');
    await files.load(fileId);
    const navigation = files.navigation;
    expect(navigation.visibleItems).toEqual(length > 4 ? [items[0], ...items.slice(-2)] : items);
    expect(navigation.omittedAncestors).toEqual(length > 4 ? items.slice(1, -2) : []);
    navigation.setMenuOpen(true);
    expect(navigation.menuOpen).toBe(length > 4);
    navigation.closeMenu();
    expect(navigation.menuOpen).toBe(false);
    expect(list).not.toHaveBeenCalled();
  });

  test('partial overflow uses only the confirmed suffix', async (): Promise<void> => {
    const { api, files } = fixture();
    const items = longPath.items.slice(1);
    vi.spyOn(api.filesystem, 'getBreadcrumbs').mockResolvedValueOnce({ items, complete: false });
    await files.load(fileId);
    expect(files.navigation.visibleItems).toEqual([items[0], ...items.slice(-2)]);
    expect(files.navigation.omittedAncestors).toEqual(items.slice(1, -2));
    expect(files.navigation.href(items[0])).not.toBe('/files');
    expect(files.navigation.label(items[0])).toBe(items[0].name);
  });

  test.each(['navigate', 'reload', 'dispose'])('closes ancestor overflow on %s', async (action): Promise<void> => {
    const { api, files } = fixture();
    vi.spyOn(api.filesystem, 'getBreadcrumbs').mockResolvedValueOnce(longPath);
    await files.load(fileId);
    files.navigation.setMenuOpen(true);
    expect(files.navigation.menuOpen).toBe(true);
    if (action === 'navigate') await files.load(null);
    else if (action === 'reload') await files.navigation.reload();
    else files.dispose();
    expect(files.navigation.menuOpen).toBe(false);
    if (action === 'dispose') {
      files.navigation.setMenuOpen(true);
      expect(files.navigation.menuOpen).toBe(false);
    }
  });
});
