import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, HttpError } from '$lib/admin/infrastructure/transport';
import { deferred, fileId, filesystemFixture, filesystemNode, folderId, rootId } from '../fixtures.test-support';
import { InMemoryFilesApi } from '../infrastructure/in-memory-api.test-support';
import type { NodeSummary } from '../domain/schemas';
import { FilesState } from './files-state.svelte';
import { RowEditingState, type RowEditingEntry } from './row-editing-state.svelte';

function fixture(): { api: InMemoryFilesApi; files: FilesState } {
  const api = new InMemoryFilesApi(rootId, filesystemFixture);
  return { api, files: new FilesState(api) };
}

async function ready(files: FilesState): Promise<RowEditingEntry> {
  await files.load(folderId);
  await vi.waitFor(() => expect(files.rowEditing.controllers.get(fileId)?.description.available).toBe(true));
  await vi.waitFor(() => expect(files.rowEditing.controllers.get(fileId)?.update.canMove).toBe(true));
  return files.rowEditing.controllers.get(fileId)!;
}

function rowState(api: InMemoryFilesApi): RowEditingState {
  return new RowEditingState(api.filesystem, (): void => {}, async (): Promise<void> => {});
}

describe('table row editing', (): void => {
  test('passes the personal home boundary to row move navigation by ID after a rename', async (): Promise<void> => {
    const { api } = fixture();
    const state = new RowEditingState(api.filesystem, (): void => {}, async (): Promise<void> => {}, () => folderId);
    try {
      await api.filesystem.updateNode(folderId, 1, { name: 'Renamed home' });
      state.select([await api.filesystem.getNode(fileId)]);
      await vi.waitFor(() => expect(state.controllers.get(fileId)?.update.canMove).toBe(true));
      const update = state.controllers.get(fileId)!.update;
      update.showMove();
      await update.browse(folderId);
      expect(update.destinationName).toBe('Files');
      expect(update.navigation.displayItems.map((item) => item.id)).toEqual([folderId]);
      expect(update.navigation.parent).toBeUndefined();
      expect(update.navigation.atRoot).toBe(true);
      await update.browse(rootId);
      expect(update.destinationName).toBe('Shared files');
      expect(update.canSubmit).toBe(true);
    } finally {
      state.dispose();
    }
  });

  test('renames and edits the child description with authoritative revisions without changing the parent', async (): Promise<void> => {
    const { api, files } = fixture();
    const row = await ready(files);
    const mutation = vi.spyOn(api.filesystem, 'updateNode');
    const description = vi.spyOn(api.filesystem, 'updateDescription');
    row.description.show();
    row.description.change('Child draft');
    row.update.showRename();
    row.update.changeName('Renamed.txt');
    await row.update.submit();
    expect(files.node).toMatchObject({ id: folderId, name: 'Projects', revision: 1 });
    expect(files.children[0]).toMatchObject({ id: fileId, name: 'Renamed.txt', revision: 2 });
    expect(row.description.open).toBe(true);
    expect(row.description.draft).toBe('Child draft');
    await row.description.save();
    expect(description).toHaveBeenCalledWith(fileId, 2, { description: 'Child draft' });
    expect(mutation).toHaveBeenNthCalledWith(1, fileId, 1, { name: 'Renamed.txt' });
    expect(files.children[0]).toMatchObject({ id: fileId, revision: 3, metadata: { attributes: { description: 'Child draft' } } });
    expect(files.rowEditing.controllers.get(fileId)).toBe(row);
  });

  test('moves the child out of the listing without moving its parent', async (): Promise<void> => {
    const { api, files } = fixture();
    const row = await ready(files);
    const mutation = vi.spyOn(api.filesystem, 'updateNode');
    row.update.showMove();
    await row.update.browse(rootId);
    await row.update.submit();
    expect(mutation).toHaveBeenCalledWith(fileId, 1, { parent_id: rootId });
    expect(files.children).toEqual([]);
    expect(files.node).toMatchObject({ id: folderId, parent_id: rootId, revision: 1 });
    expect((await api.filesystem.getNode(fileId)).parent_id).toBe(rootId);
  });

  test('selects created children and preserves drafts without repeating eligibility on revisions', async (): Promise<void> => {
    const { api, files } = fixture();
    const row = await ready(files);
    const check = vi.spyOn(api.filesystem, 'checkDescriptionEligibility');
    row.update.showRename();
    row.update.changeName('Keep draft.txt');
    files.rowEditing.select([{ ...files.children[0], revision: 2, name: 'External.txt' }]);
    expect(row.update.draft).toBe('Keep draft.txt');
    expect(row.update.open).toBe(true);
    expect(check).not.toHaveBeenCalled();
    const target = files.creationTarget()!;
    const created = await api.filesystem.createFolder(folderId, { name: 'New folder', metadata: { content_type: {}, attributes: {} } });
    await files.acceptCreated(target.parentId, target.generation, created);
    await vi.waitFor(() => expect(files.rowEditing.controllers.get(created.id)?.update.canRename).toBe(true));
    expect(files.children.some((node) => node.id === created.id)).toBe(true);
  });

  test('keeps denied operations unavailable and root rename and move hidden', async (): Promise<void> => {
    const { api } = fixture();
    const state = rowState(api);
    vi.spyOn(api.filesystem, 'checkUpdateEligibility').mockRejectedValue(new HttpError(403, 'Forbidden', {}));
    state.select(filesystemFixture);
    await vi.waitFor(() => expect(state.controllers.get(fileId)?.description.eligibility).toBe('denied'));
    expect(state.controllers.get(fileId)?.update.canRename).toBe(false);
    expect(state.controllers.get(fileId)?.update.canMove).toBe(false);
    expect(state.controllers.get(rootId)?.update.canRename).toBe(false);
    expect(state.controllers.get(rootId)?.update.canMove).toBe(false);
    state.dispose();
  });

  test('exposes retry and sign-in recovery independently from rename authorization', async (): Promise<void> => {
    const { api } = fixture();
    const state = rowState(api);
    vi.spyOn(api.filesystem, 'checkUpdateEligibility').mockRejectedValue(new Error('Offline'));
    vi.spyOn(api.filesystem, 'checkDescriptionEligibility').mockRejectedValue(new AuthenticationRequiredError());
    state.select([filesystemFixture[2]]);
    await vi.waitFor(() => expect(state.controllers.get(fileId)?.update.probeFailed).toBe(true));
    expect(state.controllers.get(fileId)?.description.eligibility).toBe('sign-in');
    state.dispose();
  });

  test.each(['reset', 'dispose'] as const)('bounds eligibility and ignores stale checks after %s', async (action): Promise<void> => {
    const { api } = fixture();
    const state = rowState(api);
    const response = deferred<void>();
    const check = vi.spyOn(api.filesystem, 'checkUpdateEligibility').mockReturnValue(response.promise);
    const descriptionCheck = vi.spyOn(api.filesystem, 'checkDescriptionEligibility').mockReturnValue(response.promise);
    const nodes = Array.from({ length: 8 }, (_, index) => filesystemNode({ id: `00000000-0000-4000-8000-${String(index + 10).padStart(12, '0')}`, parent_id: folderId }));
    state.select(nodes);
    expect(check.mock.calls.length + descriptionCheck.mock.calls.length).toBe(4);
    const entry = state.controllers.get(nodes[0].id)!;
    state[action]();
    response.resolve();
    await Promise.resolve();
    await Promise.resolve();
    expect(check.mock.calls.length + descriptionCheck.mock.calls.length).toBe(4);
    expect(entry.update.canRename).toBe(false);
    expect(entry.description.available).toBe(false);
    if (action === 'dispose') {
      state.select(nodes);
      expect(state.controllers.size).toBe(0);
    } else {
      check.mockResolvedValue(undefined);
      descriptionCheck.mockResolvedValue(undefined);
      state.select(nodes);
      await vi.waitFor(() => expect(entry.update.canMove).toBe(true));
      expect(state.controllers.get(nodes[0].id)).toBe(entry);
      state.dispose();
    }
  });

  test.each(['update', 'description'] as const)('acknowledges an authoritative row reload through %s with seeded eligibility', async (operation): Promise<void> => {
    const earlier = Array.from({ length: 3 }, (_, index) => filesystemNode({ id: `00000000-0000-4000-8000-${String(index + 10).padStart(12, '0')}`, parent_id: folderId }));
    const api = new InMemoryFilesApi(rootId, [...filesystemFixture.slice(0, 2), ...earlier, filesystemFixture[2]]);
    const files = new FilesState(api);
    const row = await ready(files);
    vi.spyOn(api.filesystem, 'updateNode').mockRejectedValueOnce(new Error('Unknown outcome'));
    row.update.showRename();
    row.update.changeName('Uncertain.txt');
    await row.update.submit();
    expect(row.update.needsReload).toBe(true);
    const updateEligibility = vi.spyOn(api.filesystem, 'checkUpdateEligibility');
    const descriptionEligibility = vi.spyOn(api.filesystem, 'checkDescriptionEligibility');
    await row[operation].reload();
    expect(row.update.canRename).toBe(true);
    expect(updateEligibility).not.toHaveBeenCalled();
    expect(descriptionEligibility).not.toHaveBeenCalled();
    expect(row.update.needsReload).toBe(false);
    row.update.showRename();
    row.update.changeName('Recovered.txt');
    expect(row.update.canSubmit).toBe(true);
    await row.update.submit();
    expect(files.children.find((node) => node.id === fileId)?.name).toBe('Recovered.txt');
    files.dispose();
  });

  test.each(['failed', 'missing'] as const)('retains row uncertainty after a %s authoritative read', async (outcome): Promise<void> => {
    const { api, files } = fixture();
    const row = await ready(files);
    vi.spyOn(api.filesystem, 'updateNode').mockRejectedValueOnce(new Error('Unknown outcome'));
    row.update.showRename();
    row.update.changeName('Uncertain.txt');
    await row.update.submit();
    expect(row.update.needsReload).toBe(true);
    const listing = vi.spyOn(api.filesystem, 'listChildren');
    if (outcome === 'failed') listing.mockRejectedValueOnce(new Error('Offline'));
    else listing.mockResolvedValueOnce([]);
    await row.update.reload();
    expect(files.phase).toBe(outcome === 'failed' ? 'error' : 'ready');
    await files.load(folderId);
    await vi.waitFor(() => expect(row.update.canRename).toBe(true));
    expect(row.update.needsReload).toBe(true);
    row.update.showRename();
    expect(row.update.canSubmit).toBe(false);
    files.dispose();
  });

  test.each(['navigation', 'dispose'] as const)('does not acknowledge row reads invalidated by %s', async (action): Promise<void> => {
    const { api, files } = fixture();
    const row = await ready(files);
    vi.spyOn(api.filesystem, 'updateNode').mockRejectedValueOnce(new Error('Unknown outcome'));
    row.update.showRename();
    row.update.changeName('Uncertain.txt');
    await row.update.submit();
    const acknowledgment = vi.spyOn(row.update, 'acceptReloadedNode');
    const response = deferred<NodeSummary[]>();
    const listing = vi.spyOn(api.filesystem, 'listChildren').mockReturnValueOnce(response.promise);
    const reload = row.description.reload();
    await vi.waitFor(() => expect(listing).toHaveBeenCalled());
    if (action === 'navigation') {
      await files.load(rootId);
      await files.load(folderId);
      await vi.waitFor(() => expect(row.update.canRename).toBe(true));
    } else files.dispose();
    response.resolve([filesystemFixture[2]]);
    await reload;
    expect(acknowledgment).not.toHaveBeenCalled();
    if (action === 'navigation') expect(row.update.needsReload).toBe(true);
    files.dispose();
  });

  test('reconciles a pending rename after navigation without replacing the new selection', async (): Promise<void> => {
    const { api, files } = fixture();
    const row = await ready(files);
    const response = deferred<NodeSummary>();
    const mutation = vi.spyOn(api.filesystem, 'updateNode').mockReturnValueOnce(response.promise);
    row.update.showRename();
    row.update.changeName('Late.txt');
    const operation = row.update.submit();
    await files.load(rootId);
    expect(row.update.open).toBe(false);
    response.resolve({ ...filesystemFixture[2], name: 'Late.txt', revision: 2 });
    await operation;
    expect(files.node?.id).toBe(rootId);
    expect(files.children.map((node) => node.id)).toEqual([folderId]);
    await files.load(folderId);
    expect(files.children[0]).toMatchObject({ id: fileId, name: 'Late.txt', revision: 2 });
    expect(mutation).toHaveBeenCalledTimes(1);
    files.dispose();
  });
});
