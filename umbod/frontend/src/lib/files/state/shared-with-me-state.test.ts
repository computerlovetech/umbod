import { expect, test, vi } from 'vitest';
import type { HeaderAccountIdentityState } from '#lib/header/accountIdentity.js';
import { HttpError } from '#lib/admin/infrastructure/transport.js';
import type { NodeSummary } from '../domain/schemas';
import { deferred, fileId, filesystemFixture, filesystemNode, folderId, rootId } from '../fixtures.test-support';
import { InMemoryFilesApi } from '../infrastructure/in-memory-api.test-support';
import { FilesState, filesHref, sharedWithMeHref } from './files-state.svelte';

function account(id: string): HeaderAccountIdentityState {
  return { kind: 'visible', name: 'User', email: null, picture: null, hiddenValues: { id } };
}

test('loads discoverable shared nodes independently of namespace discovery without enabling directory actions', async (): Promise<void> => {
  const api = new InMemoryFilesApi(rootId, filesystemFixture);
  const browse = vi.spyOn(api.filesystem, 'browse');
  vi.spyOn(api.filesystem, 'listNamespaces').mockRejectedValue(new HttpError(403, 'Forbidden', {}));
  vi.spyOn(api.filesystem, 'listSharedWithMe').mockResolvedValue([
    filesystemFixture[1],
    filesystemNode({ id: fileId, permissions: { ...filesystemFixture[2].permissions, can_discover: false } })
  ]);
  const files = new FilesState(api);
  try {
    await files.load(null, '');
    expect(files.phase).toBe('ready');
    expect(files.atSharedWithMe).toBe(true);
    expect(files.children).toEqual([filesystemFixture[1]]);
    expect(files.childHref(folderId)).toBe(filesHref(folderId, folderId));
    expect(files.namespaces).toEqual([]);
    expect(files.creationTarget()).toBeUndefined();
    expect(files.rowEditing.controllers.size).toBe(0);
    expect(files.dragMove.canDrag(folderId)).toBe(false);
    expect(browse).not.toHaveBeenCalled();
  } finally { files.dispose(); }
});

test('scope changes clear shared rows and obsolete reads cannot publish across identity or navigation', async (): Promise<void> => {
  const api = new InMemoryFilesApi(rootId, filesystemFixture);
  const listing = vi.spyOn(api.filesystem, 'listSharedWithMe').mockResolvedValueOnce([filesystemFixture[2]]);
  const files = new FilesState(api);
  try {
    files.observeAccountIdentity(account('first'));
    await files.load(null, '');
    expect(files.children).toHaveLength(1);
    const firstAccount = deferred<NodeSummary[]>();
    listing.mockReturnValueOnce(firstAccount.promise);
    const stale = files.reload();
    const firstSignal = listing.mock.calls.at(-1)?.[0];

    files.observeAccountIdentity(account('second'));
    expect(firstSignal?.aborted).toBe(true);
    expect(files.atSharedWithMe).toBe(true);
    expect(files.children).toEqual([]);
    await vi.waitFor((): void => expect(files.phase).toBe('ready'));
    firstAccount.resolve([filesystemFixture[2]]);
    await stale;
    expect(files.children).toEqual([]);

    const pending = deferred<NodeSummary[]>();
    listing.mockReturnValueOnce(pending.promise);
    const leave = files.reload();
    expect(files.isCurrentTarget(null)).toBe(false);
    await files.load(null);
    pending.resolve([filesystemFixture[2]]);
    await leave;
    expect(files.node?.id).toBe(rootId);
    expect(files.children.map((node) => node.id)).toEqual([folderId]);
  } finally { files.dispose(); }
});

test('an unavailable shared entry anchor falls back to the current node, not the private parent', async (): Promise<void> => {
  const api = new InMemoryFilesApi(rootId, filesystemFixture, undefined, () => true, (node) => node.id !== folderId);
  const files = new FilesState(api);
  try {
    await files.load(fileId, folderId);
    expect(files.phase).toBe('ready');
    expect(files.navigation.visibleItems.map((item) => item.id)).toEqual([fileId]);
    expect(files.navigation.parent).toBeUndefined();
    expect(files.isCurrentTarget(fileId)).toBe(false);
  } finally { files.dispose(); }
});

test('deleting a shared file returns to the collection rather than navigating to its parent', async (): Promise<void> => {
  const api = new InMemoryFilesApi(rootId, filesystemFixture);
  const navigate = vi.fn<(href: string) => Promise<void>>().mockResolvedValue(undefined);
  const files = new FilesState(api, navigate);
  try {
    await files.load(fileId, fileId);
    expect(files.deletion.available).toBe(true);
    files.deletion.show();
    await files.deletion.confirm();
    expect(navigate).toHaveBeenCalledExactlyOnceWith(sharedWithMeHref);
  } finally { files.dispose(); }
});
