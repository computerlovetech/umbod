import { describe, expect, test, vi } from 'vitest';
import { HttpError } from '$lib/admin/infrastructure/transport';
import { InMemoryFilesApi } from '../infrastructure/in-memory-api.test-support';
import { deferred, fileId, filesystemFixture, folderId, rootId } from '../fixtures.test-support';
import type { NodeSummary } from '../domain/schemas';
import { FilesState } from './files-state.svelte';
import { NewFolderState } from './new-folder-state.svelte';
import { UploadState } from './upload-state.svelte';

async function setup(id: string = fileId): Promise<{ api: InMemoryFilesApi; files: FilesState }> {
  const api = new InMemoryFilesApi(rootId, filesystemFixture);
  const files = new FilesState(api);
  await files.load(id);
  await vi.waitFor(() => expect(files.description.available).toBe(true));
  return { api, files };
}

describe('current description state', (): void => {
  test.each([fileId, folderId])('saves and clears %s in place with authoritative metadata and revision', async (id): Promise<void> => {
    const { api, files } = await setup(id);
    const reload = vi.spyOn(api.filesystem, 'getNode');
    const children = files.children;
    files.description.show();
    files.description.change('Read before planning');
    await files.description.save();
    expect(files.description.description).toBe('Read before planning');
    expect(files.node?.revision).toBe(2);
    expect(files.children).toBe(children);
    expect(files.description.status).toBe('Description saved.');
    files.description.show();
    files.description.change('');
    await files.description.save();
    expect(files.node?.metadata.attributes).not.toHaveProperty('description');
    if (id === fileId) expect(files.node?.metadata.attributes.topic).toBe('Planning');
    expect(files.node).toEqual(await api.filesystem.getNode(id));
    expect(reload).toHaveBeenCalledTimes(1);
    files.dispose();
  });

  test('updates future deletion revisions without cancelling an open confirmation', async (): Promise<void> => {
    const { api, files } = await setup();
    await vi.waitFor(() => expect(files.deletion.available).toBe(true));
    files.deletion.show();
    const confirmation = files.deletion.confirmation;
    files.description.show();
    files.description.change('Guidance');
    await files.description.save();
    expect(files.deletion.confirmation).toBe(confirmation);
    files.deletion.cancel();
    files.deletion.show();
    expect(files.deletion.confirmation?.revision).toBe(2);
    const remove = vi.spyOn(api.filesystem, 'deleteFile');
    await files.deletion.confirm();
    expect(remove).toHaveBeenCalledWith(fileId, 2);
    files.dispose();
  });

  test('uses the complete returned authoritative payload rather than patching local attributes', async (): Promise<void> => {
    const { api, files } = await setup();
    const returned = { ...files.node!, revision: 9, metadata: { content_type: 'text/markdown', attributes: { description: 'Canonical', server: 'Retained' } } };
    vi.spyOn(api.filesystem, 'updateDescription').mockResolvedValueOnce(returned);
    files.description.show();
    files.description.change('Requested');
    await files.description.save();
    expect(files.node).toEqual(returned);
    expect(files.description.description).toBe('Canonical');
    files.dispose();
  });

  test('keeps conflict draft and requires explicit reload before another save', async (): Promise<void> => {
    const { api, files } = await setup();
    await api.filesystem.updateDescription(fileId, 1, { description: 'Elsewhere' });
    const update = vi.spyOn(api.filesystem, 'updateDescription');
    const read = vi.spyOn(api.filesystem, 'getNode');
    files.description.show();
    files.description.change('My draft');
    await files.description.save();
    expect(files.description.needsReload).toBe(true);
    expect(files.description.draft).toBe('My draft');
    expect(files.description.error).toContain('changed');
    await files.description.save();
    expect(update).toHaveBeenCalledTimes(1);
    expect(read).not.toHaveBeenCalled();
    await files.description.reload();
    expect(files.description.description).toBe('Elsewhere');
    expect(files.description.needsReload).toBe(false);
    files.dispose();
  });

  test.each(['navigate', 'dispose'])('fences pending save after %s and blocks duplicate submission', async (action): Promise<void> => {
    const { api, files } = await setup();
    const response = deferred<NodeSummary>();
    const original = files.node!;
    const update = vi.spyOn(api.filesystem, 'updateDescription').mockReturnValueOnce(response.promise);
    files.description.show();
    files.description.change('Pending');
    const saving = files.description.save();
    await files.description.save();
    files.description.cancel();
    files.description.change('Ignored');
    expect(files.description.draft).toBe('Pending');
    expect(files.description.pending).toBe(true);
    expect(update).toHaveBeenCalledTimes(1);
    if (action === 'navigate') await files.load(folderId);
    else files.dispose();
    response.resolve({ ...original, revision: 2, metadata: { ...original.metadata, attributes: { description: 'Obsolete' } } });
    await saving;
    expect(files.description.status).toBe('');
    expect(files.node?.metadata.attributes.description).not.toBe('Obsolete');
    files.dispose();
  });

  test('returning to the same node while its old save is pending cannot submit again or accept the obsolete response', async (): Promise<void> => {
    const { api, files } = await setup();
    const response = deferred<NodeSummary>();
    const original = files.node!;
    const update = vi.spyOn(api.filesystem, 'updateDescription').mockReturnValueOnce(response.promise);
    files.description.show();
    files.description.change('Old draft');
    const saving = files.description.save();
    await files.load(folderId);
    await files.load(fileId);
    await vi.waitFor(() => expect(files.description.available).toBe(true));
    files.description.show();
    await files.description.save();
    expect(files.description.open).toBe(false);
    expect(update).toHaveBeenCalledTimes(1);
    response.resolve({ ...original, revision: 2, metadata: { ...original.metadata, attributes: { description: 'Obsolete response' } } });
    await saving;
    expect(files.node?.revision).toBe(1);
    expect(files.description.status).toBe('');
    expect(files.description.description).toBe('');
    files.description.show();
    expect(files.description.open).toBe(true);
    files.description.change('Fresh draft');
    await files.description.save();
    expect(update).toHaveBeenCalledTimes(2);
    expect(files.description.description).toBe('Fresh draft');
    files.dispose();
  });

  test('hides editing until allowed and fences stale eligibility after navigation', async (): Promise<void> => {
    const { api, files } = await setup();
    const response = deferred<void>();
    vi.spyOn(api.filesystem, 'checkDescriptionEligibility').mockReturnValueOnce(response.promise).mockRejectedValueOnce(new HttpError(403, 'Forbidden', {}));
    await files.load(fileId);
    files.description.show();
    expect(files.description.available).toBe(false);
    expect(files.description.open).toBe(false);
    await files.load(folderId);
    response.resolve();
    await vi.waitFor(() => expect(files.description.eligibility).toBe('denied'));
    files.description.show();
    expect(files.description.open).toBe(false);
    files.dispose();
  });

  test('creation forms forward optional descriptions and direct drops start empty', async (): Promise<void> => {
    const { api, files } = await setup(folderId);
    await vi.waitFor(() => expect(files.uploadAvailability).toBe('allowed'));
    const folder = new NewFolderState(api, files);
    folder.show();
    folder.changeName('Described');
    folder.changeDescription('Folder guidance');
    await folder.submit();
    expect(files.children.find((node) => node.name === 'Described')?.metadata.attributes.description).toBe('Folder guidance');
    const upload = new UploadState(api, files);
    upload.show();
    upload.select([new File(['x'], 'with.txt')]);
    upload.changeDescription('File guidance');
    await upload.submit();
    expect(files.children.find((node) => node.name === 'with.txt')?.metadata.attributes.description).toBe('File guidance');
    upload.show();
    upload.changeDescription('Old draft');
    upload.cancel();
    await upload.drop([new File([], 'drop.txt')]);
    expect(files.children.find((node) => node.name === 'drop.txt')?.metadata.attributes).toEqual({});
    folder.dispose();
    upload.dispose();
    files.dispose();
  });
});
