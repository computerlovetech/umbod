import { describe, expect, test, vi } from 'vitest';
import { HttpError } from '$lib/admin/infrastructure/transport';
import { InMemoryFilesApi } from '../infrastructure/in-memory-api.test-support';
import { deferred, fileId, filesystemFixture, folderId, rootId } from '../fixtures.test-support';
import type { NodeSummary } from '../domain/schemas';
import { FilesState } from './files-state.svelte';

async function setup(id: string = fileId): Promise<{ api: InMemoryFilesApi; files: FilesState }> {
  const api = new InMemoryFilesApi(rootId, filesystemFixture);
  const files = new FilesState(api);
  await files.load(id);
  await vi.waitFor(() => expect(files.update.canRename).toBe(true));
  await vi.waitFor(() => expect(files.update.canMove).toBe(true));
  return { api, files };
}

describe('selected node updates', (): void => {
  test('moves directly to an authorized folder without opening a dialog', async (): Promise<void> => {
    const { api, files } = await setup();
    const destination = await api.filesystem.getNode(rootId);
    const update = vi.spyOn(api.filesystem, 'updateNode');
    expect(await files.update.moveTo(destination)).toBe(true);
    expect(update).toHaveBeenCalledWith(fileId, 1, { parent_id: rootId });
    expect(files.node).toMatchObject({ id: fileId, parent_id: rootId, revision: 2 });
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
    expect(await files.update.moveTo(destination)).toBe(true);
    files.dispose();
  });

  test('blocks overlapping checks, mutations and dialogs throughout a direct move', async (): Promise<void> => {
    const { api, files } = await setup();
    const destination = await api.filesystem.getNode(rootId);
    const eligibility = deferred<void>();
    const response = deferred<NodeSummary>();
    const check = vi.spyOn(api.filesystem, 'checkUpdateEligibility').mockReturnValueOnce(eligibility.promise);
    const update = vi.spyOn(api.filesystem, 'updateNode').mockReturnValueOnce(response.promise);
    const moving = files.update.moveTo(destination);
    expect(files.update.pending).toBe(true);
    expect(await files.update.moveTo(destination)).toBe(false);
    files.update.showRename();
    files.update.showMove();
    await files.update.submit();
    expect(files.update.open).toBe(false);
    expect(files.update.canSubmit).toBe(false);
    expect(update).not.toHaveBeenCalled();
    eligibility.resolve();
    await vi.waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    expect(files.update.pending).toBe(true);
    expect(await files.update.moveTo(destination)).toBe(false);
    files.update.showRename();
    files.update.showMove();
    expect(files.update.open).toBe(false);
    expect(check).toHaveBeenCalledTimes(1);
    response.resolve({ ...files.node!, parent_id: rootId, revision: 2 });
    expect(await moving).toBe(true);
    expect(files.update.pending).toBe(false);
    files.dispose();
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
    eligibility.resolve();
    expect(await moving).toBe(false);
    expect(update).not.toHaveBeenCalled();
    expect(files.update.pending).toBe(false);
    files.dispose();
  });

  test('returns false for a stale direct move while reconciling its confirmed result', async (): Promise<void> => {
    const { api, files } = await setup();
    const original = files.node!;
    const destination = await api.filesystem.getNode(rootId);
    const response = deferred<NodeSummary>();
    const update = vi.spyOn(api.filesystem, 'updateNode').mockReturnValueOnce(response.promise);
    const moving = files.update.moveTo(destination);
    await vi.waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    await files.load(folderId);
    await files.load(fileId);
    await vi.waitFor(() => expect(files.update.canMove).toBe(true));
    expect(files.update.pending).toBe(true);
    expect(await files.update.moveTo(destination)).toBe(false);
    response.resolve({ ...original, parent_id: rootId, revision: 2 });
    expect(await moving).toBe(false);
    expect(files.node).toMatchObject({ id: fileId, parent_id: rootId, revision: 2 });
    expect(files.update.pending).toBe(false);
    expect(update).toHaveBeenCalledTimes(1);
    files.dispose();
  });

  test.each([409, 412, 500])('handles direct mutation failure %s and requires reload for unknown outcomes', async (status): Promise<void> => {
    const { api, files } = await setup();
    const destination = await api.filesystem.getNode(rootId);
    const update = vi.spyOn(api.filesystem, 'updateNode').mockRejectedValueOnce(new HttpError(status, 'Failed', {}));
    expect(await files.update.moveTo(destination)).toBe(false);
    expect(files.update.needsReload).toBe(status !== 409);
    expect(files.update.open).toBe(false);
    expect(files.update.pending).toBe(false);
    if (status !== 409) {
      expect(await files.update.moveTo(destination)).toBe(false);
      expect(update).toHaveBeenCalledTimes(1);
      await files.update.reload();
    }
    expect(await files.update.moveTo(destination)).toBe(true);
    files.dispose();
  });

  test.each(['direct', 'manual'])('rejects an incorrect authoritative destination for a %s move', async (mode): Promise<void> => {
    const { api, files } = await setup();
    const original = files.node!;
    const destination = await api.filesystem.getNode(rootId);
    vi.spyOn(api.filesystem, 'updateNode').mockResolvedValueOnce({ ...original, revision: 2 });
    if (mode === 'direct') expect(await files.update.moveTo(destination)).toBe(false);
    else {
      files.update.showMove();
      await files.update.browse(rootId);
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

  test('uses separate picker navigation, rejects current/self/descendants and moves to root', async (): Promise<void> => {
    const { files } = await setup();
    files.update.showMove();
    await vi.waitFor(() => expect(files.update.loading).toBe(false));
    expect(files.update.folder?.id).toBe(folderId);
    expect(files.update.canSubmit).toBe(false);
    expect(files.navigation.path?.items.at(-1)?.id).toBe(fileId);
    expect(files.update.folders.every((node) => node.kind === 'directory')).toBe(true);
    await files.update.browse(rootId);
    expect(files.update.canSubmit).toBe(true);
    await files.update.submit();
    expect(files.node).toMatchObject({ id: fileId, parent_id: rootId, revision: 2 });
    await vi.waitFor(() => expect(files.navigation.parent?.id).toBe(rootId));
    await files.load(folderId);
    await vi.waitFor(() => expect(files.update.canMove).toBe(true));
    files.update.showMove();
    await files.update.browse(folderId);
    expect(files.update.canSubmit).toBe(false);
    files.dispose();
  });

  test('rejects a known descendant destination and keeps rename eligible when source parent is denied', async (): Promise<void> => {
    const { api, files } = await setup(folderId);
    const child = await api.filesystem.createFolder(folderId, { name: 'Child', metadata: { attributes: {}, content_type: {} } });
    files.update.showMove();
    await files.update.browse(child.id);
    expect(files.update.canSubmit).toBe(false);
    files.dispose();
    const restricted = new InMemoryFilesApi(rootId, filesystemFixture, undefined, undefined, undefined, (node) => node.id !== folderId);
    const selected = new FilesState(restricted);
    await selected.load(fileId);
    await vi.waitFor(() => expect(selected.update.canRename).toBe(true));
    await vi.waitFor(() => expect(selected.update.canMove).toBe(false));
    selected.dispose();
  });

  test('starts at independently accessible source parent without querying inaccessible root', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture, undefined, undefined, (node) => node.id !== rootId);
    const files = new FilesState(api);
    const root = vi.spyOn(api.filesystem, 'getRoot');
    await files.load(fileId);
    await vi.waitFor(() => expect(files.update.canMove).toBe(true));
    files.update.showMove();
    await vi.waitFor(() => expect(files.update.loading).toBe(false));
    expect(files.update.folder?.id).toBe(folderId);
    expect(files.update.navigation.path?.complete).toBe(false);
    expect(root).not.toHaveBeenCalled();
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
    await files.update.browse(rootId);
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
    await files.update.browse(rootId);
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
    await files.update.browse(rootId);
    await files.update.submit();
    expect(files.node?.parent_id).toBe(rootId);
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
    await vi.waitFor(() => expect(files.update.loading).toBe(false));
    vi.spyOn(api.filesystem, 'checkUpdateEligibility').mockRejectedValueOnce(new HttpError(403, 'Denied', {}));
    await files.update.browse(rootId);
    expect(files.update.folder?.id).toBe(rootId);
    expect(files.update.folders.map((node) => node.id)).toContain(folderId);
    expect(files.update.canSubmit).toBe(false);
    await files.load(null);
    expect(files.update.canRename).toBe(false);
    expect(files.update.canMove).toBe(false);
    files.dispose();
  });
});
