import { describe, expect, test, vi } from 'vitest';
import { HttpError } from '$lib/admin/infrastructure/transport';
import { InMemoryFilesApi } from '../infrastructure/in-memory-api.test-support';
import { deferred, fileId, filesystemFixture, folderId, rootId } from '../fixtures.test-support';
import type { NodeSummary } from '../domain/schemas';
import { FilesState } from './files-state.svelte';
import { NodeUpdateState } from './node-update-state.svelte';

async function setup(id: string = fileId): Promise<{ api: InMemoryFilesApi; files: FilesState }> {
  const api = new InMemoryFilesApi(rootId, filesystemFixture);
  const files = new FilesState(api);
  await files.load(id);
  await vi.waitFor(() => expect(files.update.canRename).toBe(true));
  await vi.waitFor(() => expect(files.update.canMove).toBe(true));
  return { api, files };
}

async function selectDestination(state: NodeUpdateState, id: string): Promise<void> {
  await vi.waitFor(() => expect(state.destinations.loading).toBe(false));
  await state.destinations.select(id);
}

async function confirmMove(state: NodeUpdateState, destination: NodeSummary): Promise<boolean | undefined> {
  const moving = state.moveTo(destination);
  await vi.waitFor(() => expect(state.canSubmit || !state.open).toBe(true));
  if (state.canSubmit) await state.submit();
  return moving;
}

describe('selected node updates', (): void => {
  test('restores a moved row from a fresh listing after same-revision access restoration', async (): Promise<void> => {
    const { api, files } = await setup(folderId);
    try {
      const source = files.rowEditing.controllers.get(fileId)!.update;
      await vi.waitFor(() => expect(source.canMove).toBe(true));
      const originalUpdate = api.filesystem.updateNode;
      vi.spyOn(api.filesystem, 'updateNode').mockImplementationOnce(async (id, revision, body): Promise<NodeSummary> => {
        const moved = await originalUpdate(id, revision, body);
        return { ...moved, permissions: { ...moved.permissions, can_discover: false, can_write: false, can_share: false } };
      });
      expect(await confirmMove(source, await api.filesystem.getNode(rootId))).toBe(true);
      expect(files.children.some((node) => node.id === fileId)).toBe(false);
      await files.load(rootId);
      expect(files.children.find((node) => node.id === fileId)).toMatchObject({
        id: fileId, revision: 2, parent_id: rootId, permissions: { can_discover: true }
      });
    } finally { files.dispose(); }
  });

  test('treats a confirmed move with lost discovery as success and clears private state without ancestor requests', async (): Promise<void> => {
    const { api, files } = await setup();
    try {
      const original = files.node!;
      const destination = await api.filesystem.getNode(rootId);
      const moved = { ...original, parent_id: rootId, revision: 2, permissions: { ...original.permissions, can_discover: false, can_write: false, can_share: false } };
      const patch = vi.spyOn(api.filesystem, 'updateNode').mockResolvedValueOnce(moved);
      const ancestors = vi.spyOn(api.filesystem, 'getBreadcrumbs');
      const browse = vi.spyOn(api.filesystem, 'browse');
      expect(await confirmMove(files.update, destination)).toBe(true);
      expect(patch).toHaveBeenCalledOnce();
      expect(files.phase).toBe('missing');
      expect(files.node).toBeUndefined();
      expect(files.children).toEqual([]);
      expect(files.navigation.path).toBeUndefined();
      expect(files.update.canRename).toBe(false);
      expect(files.update.canMove).toBe(false);
      expect(files.description.available).toBe(false);
      expect(files.deletion.available).toBe(false);
      expect(files.sharing.available(fileId)).toBe(false);
      expect(ancestors).not.toHaveBeenCalled();
      expect(browse).not.toHaveBeenCalled();
      expect(files.update.needsReload).toBe(false);
    } finally { files.dispose(); }
  });

  test('refreshes moved selection capabilities without ancestor probes and revokes stale mutation controls', async (): Promise<void> => {
    const { api, files } = await setup();
    try {
      const original = files.node!;
      const destination = await api.filesystem.getNode(rootId);
      const moved = { ...original, parent_id: rootId, revision: 2, permissions: { ...original.permissions, can_write: false, can_share: false, can_delete: false } };
      vi.spyOn(api.filesystem, 'updateNode').mockResolvedValueOnce(moved);
      const gate = deferred<Awaited<ReturnType<typeof api.filesystem.browse>>>();
      const browse = vi.spyOn(api.filesystem, 'browse').mockReturnValueOnce(gate.promise);
      const ancestors = vi.spyOn(api.filesystem, 'getBreadcrumbs');
      expect(await confirmMove(files.update, destination)).toBe(true);
      expect(files.update.canRename).toBe(false);
      expect(files.description.available).toBe(false);
      expect(files.sharing.available(fileId)).toBe(false);
      expect(ancestors).not.toHaveBeenCalled();
      gate.resolve({
        node: moved, entries: [], truncated: false,
        breadcrumbs: { items: [{ id: fileId, name: moved.name, kind: 'file' }], complete: false },
        capabilities: [{ node_id: fileId, rename: false, move: false, edit_description: false, delete: false, share: false, upload: false, create_directory: false }]
      });
      await vi.waitFor(() => expect(files.phase).toBe('ready'));
      expect(files.node).toEqual(moved);
      expect(files.update.canRename).toBe(false);
      expect(files.update.canMove).toBe(false);
      expect(files.description.available).toBe(false);
      expect(files.deletion.available).toBe(false);
      expect(files.sharing.available(fileId)).toBe(false);
      expect(browse).toHaveBeenCalledExactlyOnceWith(fileId, expect.any(AbortSignal));
      expect(ancestors).not.toHaveBeenCalled();
    } finally { files.dispose(); }
  });

  test('keeps the renamed home boundary in the picker while retaining raw ancestors for descendant checks', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    let personalRoot = folderId;
    const state = new NodeUpdateState(api.filesystem, (): void => {}, async (): Promise<void> => {}, () => personalRoot);
    try {
      await api.filesystem.updateNode(folderId, 1, { name: 'Renamed personal storage' });
      await state.select(await api.filesystem.getNode(fileId), { rename: true, move: true });
      state.showMove();
      await vi.waitFor(() => expect(state.destinations.loading).toBe(false));
      expect(state.destinations.folders).toMatchObject([{ id: folderId, name: 'Home', current: true, selectable: false }]);
      expect(state.destinations.selected).toBeUndefined();
      await state.destinations.select(folderId);
      expect(state.canSubmit).toBe(false);
      await state.destinations.select(rootId);
      expect(state.destinations.selected).toBeUndefined();
      expect(state.canSubmit).toBe(false);
      const child = await api.filesystem.createFolder(folderId, { name: 'Nested', metadata: { content_type: {}, attributes: {} } });
      personalRoot = child.id;
      const rootChildren = await api.filesystem.listChildren(rootId);
      vi.spyOn(api.filesystem, 'listChildren').mockResolvedValueOnce([...rootChildren, { ...child, parent_id: rootId }]);
      await state.select(await api.filesystem.getNode(folderId), { rename: true, move: true });
      state.showMove();
      await vi.waitFor(() => expect(state.destinations.loading).toBe(false));
      expect(state.destinations.folders[0]).toMatchObject({ id: rootId, name: 'Root', children: [{ id: child.id, name: 'Home', selectable: true }] });
      await state.destinations.select(child.id);
      expect(state.destinations.selected).toBeUndefined();
      expect(state.canSubmit).toBe(false);
    } finally {
      state.dispose();
    }
  });

  test('moves to an authorized folder after explicit confirmation', async (): Promise<void> => {
    const { api, files } = await setup();
    const destination = await api.filesystem.getNode(rootId);
    const update = vi.spyOn(api.filesystem, 'updateNode');
    expect(await confirmMove(files.update, destination)).toBe(true);
    expect(update).toHaveBeenCalledWith(fileId, 1, { parent_id: rootId });
    await vi.waitFor(() => expect(files.node).toMatchObject({ id: fileId, parent_id: rootId, revision: 2 }));
    expect(files.update.open).toBe(false);
    expect(files.update.pending).toBe(false);
    files.dispose();
  });

  test.each([403, 404, 500])('retries destination check failure %s without revoking source eligibility', async (status): Promise<void> => {
    const { api, files } = await setup();
    const destination = await api.filesystem.getNode(rootId);
    vi.spyOn(api.filesystem, 'checkUpdateEligibility').mockRejectedValueOnce(new HttpError(status, 'Denied', {}));
    const update = vi.spyOn(api.filesystem, 'updateNode');
    expect(await files.update.moveTo(destination)).toBe(false);
    expect(update).not.toHaveBeenCalled();
    expect(files.update.error).toBe(status === 500 ? 'Could not check destination. Try again.' : 'You cannot move items to this folder.');
    expect(files.update.canMove).toBe(true);
    expect(files.update.canRename).toBe(true);
    expect(files.update.needsReload).toBe(false);
    expect(files.update.pending).toBe(false);
    expect(await confirmMove(files.update, destination)).toBe(true);
    files.dispose();
  });

  test('stages native moves without saving, prevents duplicate reviews and cancels cleanly', async (): Promise<void> => {
    const { api, files } = await setup();
    try {
      const destination = await api.filesystem.getNode(rootId);
      const patch = vi.spyOn(api.filesystem, 'updateNode');
      const moving = files.update.moveTo(destination);
      await vi.waitFor(() => expect(files.update.canSubmit).toBe(true));
      expect(files.update.pending).toBe(false);
      expect(files.update.open).toBe(true);
      expect(files.update.moveWarning).toBe('Moving this item may change inherited access. Direct sharing remains unchanged.');
      expect(await files.update.moveTo(destination)).toBe(false);
      files.update.showRename();
      expect(files.update.moving).toBe(true);
      expect(patch).not.toHaveBeenCalled();
      files.update.cancel();
      expect(await moving).toBeUndefined();
      expect(files.update.error).toBe('');
      expect(patch).not.toHaveBeenCalled();
    } finally { files.dispose(); }
  });

  test.each(['navigation', 'disposal'])('does not mutate after %s during destination authorization', async (action): Promise<void> => {
    const { api, files } = await setup();
    const destination = await api.filesystem.getNode(rootId);
    const eligibility = deferred<void>();
    vi.spyOn(api.filesystem, 'checkUpdateEligibility').mockReturnValueOnce(eligibility.promise);
    const update = vi.spyOn(api.filesystem, 'updateNode');
    const moving = files.update.moveTo(destination);
    if (action === 'navigation') await files.load(folderId);
    else files.dispose();
    expect(await moving).toBeUndefined();
    eligibility.resolve();
    expect(update).not.toHaveBeenCalled();
    expect(files.update.pending).toBe(false);
    files.dispose();
  });

  test('returns success for a stale direct move while reconciling its confirmed result', async (): Promise<void> => {
    const { api, files } = await setup();
    const original = files.node!;
    const destination = await api.filesystem.getNode(rootId);
    const response = deferred<NodeSummary>();
    const update = vi.spyOn(api.filesystem, 'updateNode').mockReturnValueOnce(response.promise);
    const moving = confirmMove(files.update, destination);
    await vi.waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    await files.load(folderId);
    await files.load(fileId);
    await vi.waitFor(() => expect(files.update.canMove).toBe(true));
    expect(files.update.pending).toBe(true);
    expect(await files.update.moveTo(destination)).toBe(false);
    response.resolve({ ...original, parent_id: rootId, revision: 2 });
    expect(await moving).toBe(true);
    await vi.waitFor(() => expect(files.node).toMatchObject({ id: fileId, parent_id: rootId, revision: 2 }));
    expect(files.update.pending).toBe(false);
    expect(update).toHaveBeenCalledTimes(1);
    files.dispose();
  });

  test.each([409, 412, 500])('handles direct mutation failure %s and requires reload for unknown outcomes', async (status): Promise<void> => {
    const { api, files } = await setup();
    const destination = await api.filesystem.getNode(rootId);
    const update = vi.spyOn(api.filesystem, 'updateNode').mockRejectedValueOnce(new HttpError(status, 'Failed', {}));
    expect(await confirmMove(files.update, destination)).toBe(false);
    expect(files.update.needsReload).toBe(status !== 409);
    expect(files.update.open).toBe(true);
    files.update.cancel();
    expect(files.update.pending).toBe(false);
    if (status !== 409) {
      expect(await confirmMove(files.update, destination)).toBe(false);
      expect(update).toHaveBeenCalledTimes(1);
      await files.update.reload();
    }
    expect(await confirmMove(files.update, destination)).toBe(true);
    files.dispose();
  });

  test.each(['direct', 'manual'])('rejects an incorrect authoritative destination for a %s move', async (mode): Promise<void> => {
    const { api, files } = await setup();
    const original = files.node!;
    const destination = await api.filesystem.getNode(rootId);
    vi.spyOn(api.filesystem, 'updateNode').mockResolvedValueOnce({ ...original, revision: 2 });
    if (mode === 'direct') expect(await confirmMove(files.update, destination)).toBe(false);
    else {
      files.update.showMove();
      await selectDestination(files.update, rootId);
      await files.update.submit();
    }
    expect(files.node).toEqual(original);
    expect(files.update.needsReload).toBe(true);
    expect(files.update.error).toBe('The update could not be confirmed. Reload before trying again.');
    expect(files.update.canSubmit).toBe(false);
    files.dispose();
  });

  test('rejects direct moves for invalid targets, directory sources and open dialogs', async (): Promise<void> => {
    const { api, files } = await setup();
    const destination = await api.filesystem.getNode(rootId);
    const update = vi.spyOn(api.filesystem, 'updateNode');
    expect(await files.update.moveTo(files.node!)).toBe(false);
    expect(await files.update.moveTo(await api.filesystem.getNode(folderId))).toBe(false);
    files.update.showRename();
    expect(await files.update.moveTo(destination)).toBe(false);
    files.update.cancel();
    files.update.showMove();
    expect(await files.update.moveTo(destination)).toBe(false);
    await files.load(folderId);
    await vi.waitFor(() => expect(files.update.canMove).toBe(true));
    expect(await files.update.moveTo(destination)).toBe(false);
    expect(update).not.toHaveBeenCalled();
    files.dispose();
  });

  test('reconciles name, selected path and future description and deletion revisions', async (): Promise<void> => {
    const { api, files } = await setup();
    files.update.showRename();
    expect(files.update.draft).toBe('Notes.txt');
    files.update.changeName('Renamed.txt');
    await files.update.submit();
    expect(files.node).toMatchObject({ id: fileId, name: 'Renamed.txt', revision: 2 });
    await vi.waitFor(() => expect(files.navigation.path?.items.at(-1)?.name).toBe('Renamed.txt'));
    files.description.show();
    files.description.change('Description');
    const update = vi.spyOn(api.filesystem, 'updateDescription');
    await files.description.save();
    expect(update).toHaveBeenCalledWith(fileId, 2, { description: 'Description' });
    files.deletion.show();
    expect(files.deletion.confirmation?.revision).toBe(3);
    files.dispose();
  });

  test('keeps picker selection separate, disables the current folder and excludes the source directory', async (): Promise<void> => {
    const { files } = await setup();
    files.update.showMove();
    await vi.waitFor(() => expect(files.update.destinations.loading).toBe(false));
    expect(files.update.destinations.folders).toMatchObject([{ id: rootId, name: 'Home', children: [{ id: folderId, current: true, selectable: false }] }]);
    expect(files.update.destinations.selected).toBeUndefined();
    expect(files.update.canSubmit).toBe(false);
    expect(files.navigation.path?.items.at(-1)?.id).toBe(fileId);
    await files.update.destinations.select(folderId);
    expect(files.update.destinations.selected).toBeUndefined();
    expect(files.update.canSubmit).toBe(false);
    await selectDestination(files.update, rootId);
    expect(files.update.canSubmit).toBe(true);
    await files.update.submit();
    await vi.waitFor(() => expect(files.node).toMatchObject({ id: fileId, parent_id: rootId, revision: 2 }));
    await vi.waitFor(() => expect(files.navigation.parent?.id).toBe(rootId));
    await files.load(folderId);
    await vi.waitFor(() => expect(files.update.canMove).toBe(true));
    files.update.showMove();
    await vi.waitFor(() => expect(files.update.destinations.loading).toBe(false));
    expect(files.update.destinations.folders[0]).toMatchObject({ id: rootId, current: true, selectable: false, children: [] });
    await files.update.destinations.select(folderId);
    expect(files.update.destinations.selected).toBeUndefined();
    expect(files.update.canSubmit).toBe(false);
    files.dispose();
  });

  test('excludes descendant destinations and keeps rename eligible when source parent is denied', async (): Promise<void> => {
    const { api, files } = await setup(folderId);
    const child = await api.filesystem.createFolder(folderId, { name: 'Child', metadata: { attributes: {}, content_type: {} } });
    files.update.showMove();
    await vi.waitFor(() => expect(files.update.destinations.loading).toBe(false));
    expect(files.update.destinations.folders[0].children).toEqual([]);
    await files.update.destinations.select(child.id);
    expect(files.update.destinations.selected).toBeUndefined();
    expect(files.update.canSubmit).toBe(false);
    files.dispose();
    const restricted = new InMemoryFilesApi(rootId, filesystemFixture, undefined, undefined, undefined, (node) => node.id !== folderId);
    const selected = new FilesState(restricted);
    await selected.load(fileId);
    await vi.waitFor(() => expect(selected.update.canRename).toBe(true));
    await vi.waitFor(() => expect(selected.update.canMove).toBe(false));
    selected.dispose();
  });

  test('displays an independently accessible source parent without querying inaccessible root', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture, undefined, undefined, (node) => node.id !== rootId);
    const files = new FilesState(api);
    const root = vi.spyOn(api.filesystem, 'browse');
    await files.load(fileId);
    await vi.waitFor(() => expect(files.update.canMove).toBe(true));
    files.update.showMove();
    await vi.waitFor(() => expect(files.update.destinations.loading).toBe(false));
    expect(files.update.destinations.folders).toMatchObject([{ id: folderId, name: 'Projects', current: true, selectable: false }]);
    expect(files.update.destinations.selected).toBeUndefined();
    expect(files.update.canSubmit).toBe(false);
    expect(root.mock.calls.map(([target]) => target)).not.toContain(null);
    files.dispose();
  });

  test.each([409, 412, 500])('preserves draft after %s and explicitly reloads uncertain outcomes', async (status): Promise<void> => {
    const { api, files } = await setup();
    vi.spyOn(api.filesystem, 'updateNode').mockRejectedValueOnce(new HttpError(status, 'Failed', {}));
    const reload = vi.spyOn(api.filesystem, 'getNode');
    files.update.showRename();
    files.update.changeName('Draft');
    await files.update.submit();
    expect(files.update.draft).toBe('Draft');
    expect(files.update.needsReload).toBe(status !== 409);
    expect(files.update.canSubmit).toBe(status === 409);
    expect(reload).not.toHaveBeenCalled();
    if (status !== 409) await files.update.reload();
    expect(files.update.needsReload).toBe(false);
    files.dispose();
  });

  test('prevents duplicate mutation across navigation and retains authoritative result against stale reload', async (): Promise<void> => {
    const { api, files } = await setup();
    const original = files.node!;
    const response = deferred<NodeSummary>();
    const update = vi.spyOn(api.filesystem, 'updateNode').mockReturnValueOnce(response.promise);
    files.update.showRename();
    files.update.changeName('Authoritative');
    const saving = files.update.submit();
    await files.update.submit();
    await files.load(folderId);
    await files.load(fileId);
    await vi.waitFor(() => expect(files.update.canRename).toBe(true));
    files.update.showRename();
    expect(files.update.open).toBe(false);
    response.resolve({ ...original, name: 'Authoritative', revision: 2 });
    await saving;
    expect(update).toHaveBeenCalledTimes(1);
    expect(files.node?.name).toBe('Authoritative');
    await files.reload();
    expect(files.node?.name).toBe('Authoritative');
    files.dispose();
  });

  test.each(['listing-first', 'mutation-first'])('inserts confirmed moves omitted by destination listing with %s and filters stale source rows', async (order): Promise<void> => {
    const { api, files } = await setup();
    const original = files.node!;
    const updated = { ...original, parent_id: rootId, name: 'Moved.txt', revision: 2 };
    files.update.showMove();
    await selectDestination(files.update, rootId);
    const response = deferred<NodeSummary>();
    vi.spyOn(api.filesystem, 'updateNode').mockReturnValueOnce(response.promise);
    const saving = files.update.submit();
    const listing = deferred<NodeSummary[]>();
    const list = vi.spyOn(api.filesystem, 'listChildren').mockReturnValueOnce(listing.promise);
    const inspect = vi.spyOn(api.sharing, 'inspectAccess');
    const loading = files.load(rootId);
    await vi.waitFor(() => expect(list).toHaveBeenCalledWith(rootId, expect.any(AbortSignal)));
    if (order === 'listing-first') {
      listing.resolve([filesystemFixture[1]]);
      await loading;
      expect(files.children.some((child) => child.id === fileId)).toBe(false);
      response.resolve(updated);
      await saving;
    } else {
      response.resolve(updated);
      await saving;
      expect(files.phase).toBe('loading');
      expect(files.children).toEqual([]);
      listing.resolve([filesystemFixture[1]]);
      await loading;
    }
    expect(files.children.find((child) => child.id === fileId)).toEqual(updated);
    await vi.waitFor(() => expect(files.rowDeletion.controllers.get(fileId)?.available).toBe(true));
    files.rowDeletion.controllers.get(fileId)?.show();
    expect(files.rowDeletion.controllers.get(fileId)?.confirmation?.revision).toBe(2);
    expect(inspect.mock.calls.some(([id]) => id === fileId)).toBe(true);
    list.mockResolvedValueOnce([original]);
    await files.load(folderId);
    expect(files.children).toEqual([]);
    files.dispose();
  });

  test.each(['listing-first', 'mutation-first'])('keeps newer destination listing revisions with %s and never inserts an older cached revision', async (order): Promise<void> => {
    const { api, files } = await setup();
    const original = files.node!;
    const updated = { ...original, parent_id: rootId, revision: 2 };
    const newer = { ...updated, name: 'Newer.txt', revision: 3 };
    files.update.showMove();
    await selectDestination(files.update, rootId);
    const response = deferred<NodeSummary>();
    vi.spyOn(api.filesystem, 'updateNode').mockReturnValueOnce(response.promise);
    const saving = files.update.submit();
    const listing = deferred<NodeSummary[]>();
    const list = vi.spyOn(api.filesystem, 'listChildren').mockReturnValueOnce(listing.promise);
    const loading = files.load(rootId);
    await vi.waitFor(() => expect(list).toHaveBeenCalledWith(rootId, expect.any(AbortSignal)));
    if (order === 'listing-first') {
      listing.resolve([filesystemFixture[1], newer]);
      await loading;
      response.resolve(updated);
      await saving;
    } else {
      response.resolve(updated);
      await saving;
      listing.resolve([filesystemFixture[1], newer]);
      await loading;
    }
    expect(files.children.find((child) => child.id === fileId)).toEqual(newer);
    list.mockResolvedValueOnce([filesystemFixture[1]]);
    await files.reload();
    expect(files.children.some((child) => child.id === fileId)).toBe(false);
    files.dispose();
  });

  test('respects fresh destination absence after a successful move and does not resurrect revoked or deleted rows', async (): Promise<void> => {
    const { api, files } = await setup();
    files.update.showMove();
    await selectDestination(files.update, rootId);
    await files.update.submit();
    await vi.waitFor(() => expect(files.node?.parent_id).toBe(rootId));
    const list = vi.spyOn(api.filesystem, 'listChildren').mockResolvedValue([filesystemFixture[1]]);
    await files.load(rootId);
    expect(files.children.map((child) => child.id)).toEqual([folderId]);
    expect(files.rowDeletion.controllers.has(fileId)).toBe(false);
    await files.reload();
    expect(files.children.map((child) => child.id)).toEqual([folderId]);
    expect(list).toHaveBeenCalledTimes(2);
    files.dispose();
  });

  test('hides root and denied actions, distinguishes destination browsing from selection and retries probe errors', async (): Promise<void> => {
    const { api, files } = await setup();
    vi.spyOn(api.filesystem, 'checkUpdateEligibility').mockRejectedValueOnce(new Error('Offline'));
    await files.update.checkEligibility();
    expect(files.update.probeFailed).toBe(true);
    await files.update.checkEligibility();
    expect(files.update.canMove).toBe(true);
    files.update.showMove();
    await vi.waitFor(() => expect(files.update.destinations.loading).toBe(false));
    expect(files.update.destinations.selected).toBeUndefined();
    expect(files.update.canSubmit).toBe(false);
    vi.spyOn(api.filesystem, 'checkUpdateEligibility').mockRejectedValueOnce(new HttpError(403, 'Denied', {}));
    await files.update.destinations.select(rootId);
    expect(files.update.destinations.folders[0]).toMatchObject({ id: rootId, selectable: false, children: [{ id: folderId }] });
    expect(files.update.destinations.selected).toBeUndefined();
    expect(files.update.canSubmit).toBe(false);
    await files.load(null);
    expect(files.update.canRename).toBe(false);
    expect(files.update.canMove).toBe(false);
    files.dispose();
  });
});
