import { Window } from 'happy-dom';
import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, HttpError, NetworkError } from '$lib/admin/infrastructure/transport';
import { deferred, fileId, filesystemFixture, filesystemNode, folderId, rootId } from '../fixtures.test-support';
import { InMemoryFilesApi } from '../infrastructure/in-memory-api.test-support';
import { UploadState } from './upload-state.svelte';
import { FilesState } from './files-state.svelte';
import type { DeletionState } from './deletion-state.svelte';

const secondId = '00000000-0000-4000-8000-000000000004';

function fixture(): { api: InMemoryFilesApi; files: FilesState } {
  const api = new InMemoryFilesApi(rootId, [...filesystemFixture, filesystemNode({ id: secondId, kind: 'file', parent_id: folderId, name: 'Second.txt' })]);
  return { api, files: new FilesState(api) };
}

async function ready(files: FilesState, id: string = fileId): Promise<DeletionState> {
  await files.load(folderId);
  await vi.waitFor(() => expect(files.rowDeletion.controllers.get(id)?.available).toBe(true));
  return files.rowDeletion.controllers.get(id)!;
}

describe('table row deletion', (): void => {
  test.each(['before-listing', 'after-listing'])('reconciles concurrent confirmed deletions when the second finishes %s', async (timing): Promise<void> => {
    const { api, files } = fixture();
    const first = await ready(files);
    const second = files.rowDeletion.controllers.get(secondId)!;
    const firstResponse = deferred<void>();
    const secondResponse = deferred<void>();
    const original = api.filesystem.deleteFile;
    const remove = vi.spyOn(api.filesystem, 'deleteFile').mockImplementation(async (id, revision): Promise<void> => {
      await (id === fileId ? firstResponse.promise : secondResponse.promise);
      await original(id, revision);
    });
    first.show();
    const firstOperation = first.confirm();
    second.show();
    const secondOperation = second.confirm();
    const staleListing = files.children.filter((node) => node.id !== fileId);
    const listingResponse = deferred<typeof staleListing>();
    vi.spyOn(api.filesystem, 'listChildren').mockReturnValueOnce(listingResponse.promise);
    firstResponse.resolve();
    await vi.waitFor(() => expect(files.phase).toBe('loading'));
    if (timing === 'before-listing') {
      secondResponse.resolve();
      await secondOperation;
    }
    listingResponse.resolve(staleListing);
    await firstOperation;
    if (timing === 'after-listing') {
      expect(files.children.map((node) => node.id)).toEqual([secondId]);
      secondResponse.resolve();
      await secondOperation;
    }
    expect(files.node?.id).toBe(folderId);
    expect(files.children).toEqual([]);
    expect(files.mutationNotice).toBe('“Second.txt” was deleted from the workspace.');
    first.show();
    second.show();
    await first.confirm();
    await second.confirm();
    expect(remove).toHaveBeenCalledTimes(2);
  });

  test('checks a publicly uploaded file and deletes it immediately without reloading or navigation', async (): Promise<void> => {
    const { api, files } = fixture();
    await ready(files);
    const existing = files.rowDeletion.controllers.get(fileId);
    const check = vi.spyOn(api.filesystem, 'checkDeleteEligibility');
    const upload = new UploadState(api, files);
    await vi.waitFor(() => expect(upload.available).toBe(true));
    upload.show();
    upload.select([new File(['new'], 'Uploaded.txt', { type: 'text/plain' })]);
    await upload.submit();
    const created = files.children.find((node) => node.name === 'Uploaded.txt')!;
    expect(created).toBeDefined();
    await vi.waitFor(() => expect(files.rowDeletion.controllers.get(created.id)?.available).toBe(true));
    expect(check).toHaveBeenCalledExactlyOnceWith(created.id, expect.any(AbortSignal));
    expect(files.rowDeletion.controllers.get(fileId)).toBe(existing);
    expect(existing?.available).toBe(true);
    const row = files.rowDeletion.controllers.get(created.id)!;
    row.show();
    await files.rowDeletion.confirm(created.id);
    expect(files.children.some((node) => node.id === created.id)).toBe(false);
    expect(files.node?.id).toBe(folderId);
  });

  test('queues upload eligibility behind existing row checks without resetting them or exceeding the limit', async (): Promise<void> => {
    const extra = Array.from({ length: 5 }, (_, index) => filesystemNode({
      id: `00000000-0000-4000-8000-${String(index + 10).padStart(12, '0')}`,
      kind: 'file', parent_id: folderId, name: `Queued ${index}`
    }));
    const api = new InMemoryFilesApi(rootId, [...filesystemFixture, ...extra]);
    const files = new FilesState(api);
    const eligibility = deferred<void>();
    const check = vi.spyOn(api.filesystem, 'checkDeleteEligibility').mockReturnValue(eligibility.promise);
    await files.load(folderId);
    expect(check).toHaveBeenCalledTimes(4);
    const upload = new UploadState(api, files);
    await vi.waitFor(() => expect(upload.available).toBe(true));
    upload.show();
    upload.select([new File(['new'], 'Queued upload.txt', { type: 'text/plain' })]);
    await upload.submit();
    const created = files.children.find((node) => node.name === 'Queued upload.txt')!;
    expect(check).toHaveBeenCalledTimes(4);
    eligibility.resolve();
    await vi.waitFor(() => expect(files.rowDeletion.controllers.get(created.id)?.available).toBe(true));
    expect(check).toHaveBeenCalledTimes(7);
    expect(new Set(check.mock.calls.map(([id]) => id)).size).toBe(7);
  });

  test.each([new HttpError(412, 'Changed', {}), new NetworkError(new Error('Lost response'))])('focuses row recovery after %s', async (error): Promise<void> => {
    const { api, files } = fixture();
    const row = await ready(files);
    const window = new Window();
    const recovery = window.document.createElement('button');
    window.document.body.append(recovery);
    const detach = files.rowDeletion.attachRecovery(fileId)(recovery as unknown as HTMLElement);
    vi.spyOn(api.filesystem, 'deleteFile').mockRejectedValueOnce(error);
    row.show();
    await files.rowDeletion.confirm(fileId);
    expect(row.needsReload).toBe(true);
    expect(window.document.activeElement).toBe(recovery);
    detach();
  });

  test.each(['navigate', 'dispose'])('does not focus stale row recovery after %s', async (action): Promise<void> => {
    const { api, files } = fixture();
    const row = await ready(files);
    const window = new Window();
    const recovery = window.document.createElement('button');
    window.document.body.append(recovery);
    const focus = vi.spyOn(recovery, 'focus');
    files.rowDeletion.attachRecovery(fileId)(recovery as unknown as HTMLElement);
    const response = deferred<void>();
    vi.spyOn(api.filesystem, 'deleteFile').mockReturnValueOnce(response.promise);
    row.show();
    const operation = files.rowDeletion.confirm(fileId);
    if (action === 'dispose') files.dispose();
    else await files.load(rootId);
    response.reject(new HttpError(412, 'Changed', {}));
    await operation;
    expect(focus).not.toHaveBeenCalled();
  });

  test('cancels the captured row without deleting or changing directory', async (): Promise<void> => {
    const { api, files } = fixture();
    const remove = vi.spyOn(api.filesystem, 'deleteFile');
    const row = await ready(files);
    row.show();
    expect(row.confirmation?.name).toBe('Notes.txt');
    await files.rowDeletion.cancel(fileId);
    await row.confirm();
    expect(remove).not.toHaveBeenCalled();
    expect(files.node?.id).toBe(folderId);
  });

  test('deletes the row, reloads the same folder and reports its filename without navigation', async (): Promise<void> => {
    const { api } = fixture();
    const navigate = vi.fn();
    const files = new FilesState(api, navigate);
    const listing = vi.spyOn(api.filesystem, 'listChildren');
    const row = await ready(files);
    row.show();
    await row.confirm();
    expect(files.node?.id).toBe(folderId);
    expect(files.children.map((node) => node.id)).toEqual([secondId]);
    expect(files.mutationNotice).toContain('“Notes.txt” was deleted');
    expect(listing).toHaveBeenCalledTimes(2);
    expect(navigate).not.toHaveBeenCalled();
  });

  test('retains success and offers only read recovery when the table refresh fails', async (): Promise<void> => {
    const { api, files } = fixture();
    const row = await ready(files);
    const remove = vi.spyOn(api.filesystem, 'deleteFile');
    vi.spyOn(api.filesystem, 'listChildren').mockRejectedValueOnce(new HttpError(500, 'Unavailable', {}));
    row.show();
    await row.confirm();
    expect(files.phase).toBe('error');
    expect(files.mutationNotice).toContain('Notes.txt');
    expect(row.message).toBe('');
    await files.reload();
    expect(files.children.map((node) => node.id)).toEqual([secondId]);
    expect(remove).toHaveBeenCalledTimes(1);
  });

  test.each([new HttpError(412, 'Changed', {}), new HttpError(403, 'Forbidden', {}), new AuthenticationRequiredError(), new NetworkError(new Error('Lost response'))])('reconciles %s without automatically repeating DELETE', async (error): Promise<void> => {
    const { api, files } = fixture();
    const row = await ready(files);
    const remove = vi.spyOn(api.filesystem, 'deleteFile').mockRejectedValueOnce(error);
    row.show();
    await row.confirm();
    expect(row.needsReload).toBe(true);
    expect(row.available).toBe(false);
    expect(row.message).not.toBe('');
    row.show();
    await row.confirm();
    expect(remove).toHaveBeenCalledTimes(1);
    await row.reconcile();
    expect(files.node?.id).toBe(folderId);
    expect(files.children).toHaveLength(2);
    expect(remove).toHaveBeenCalledTimes(1);
  });

  test('reconciles an uncertain successful deletion through listing rather than another mutation', async (): Promise<void> => {
    const { api, files } = fixture();
    const row = await ready(files);
    const original = api.filesystem.deleteFile;
    const remove = vi.spyOn(api.filesystem, 'deleteFile').mockImplementation(async (id, revision): Promise<void> => {
      await original(id, revision);
      throw new NetworkError(new Error('Lost response'));
    });
    row.show();
    await row.confirm();
    await row.reconcile();
    expect(files.children.map((node) => node.id)).toEqual([secondId]);
    expect(files.mutationNotice).toBe('');
    expect(remove).toHaveBeenCalledTimes(1);
  });

  test('retains same-node duplicate protection through reload and navigation without blocking other rows', async (): Promise<void> => {
    const { api, files } = fixture();
    const row = await ready(files);
    const response = deferred<void>();
    const remove = vi.spyOn(api.filesystem, 'deleteFile').mockReturnValueOnce(response.promise);
    row.show();
    const operation = row.confirm();
    await row.confirm();
    expect(files.rowDeletion.controllers.get(secondId)?.pending).toBe(false);
    expect(files.rowDeletion.controllers.get(secondId)?.available).toBe(true);
    await files.load(rootId);
    await files.load(folderId);
    await vi.waitFor(() => expect(files.rowDeletion.controllers.get(fileId)?.pending).toBe(true));
    expect(files.rowDeletion.controllers.get(fileId)).toBe(row);
    row.show();
    await row.confirm();
    expect(remove).toHaveBeenCalledTimes(1);
    response.resolve();
    await operation;
    expect(row.available).toBe(false);
    expect(row.needsReload).toBe(true);
    expect(files.node?.id).toBe(folderId);
  });

  test.each(['reload', 'navigate', 'dispose'])('ignores late eligibility and mutation completions after %s', async (action): Promise<void> => {
    const { api, files } = fixture();
    const row = await ready(files);
    const response = deferred<void>();
    vi.spyOn(api.filesystem, 'deleteFile').mockReturnValueOnce(response.promise);
    row.show();
    const operation = row.confirm();
    const eligibility = deferred<void>();
    vi.spyOn(api.filesystem, 'checkDeleteEligibility').mockReturnValue(eligibility.promise);
    await files.reload();
    if (action === 'dispose') files.dispose();
    else if (action === 'navigate') await files.load(rootId);
    eligibility.resolve();
    response.resolve();
    await operation;
    expect(row.available).toBe(false);
    expect(row.confirmation).toBeUndefined();
    expect(files.mutationNotice).toBe(action === 'reload' ? '“Notes.txt” was deleted from the workspace.' : '');
    expect(files.node?.id).toBe(action === 'navigate' ? rootId : folderId);
  });

  test('protects the same node when moving from a pending row to details', async (): Promise<void> => {
    const { api, files } = fixture();
    const row = await ready(files);
    const response = deferred<void>();
    const remove = vi.spyOn(api.filesystem, 'deleteFile').mockReturnValueOnce(response.promise);
    row.show();
    const operation = row.confirm();
    await files.load(fileId);
    await vi.waitFor(() => expect(files.deletion.available).toBe(true));
    expect(files.deletion.pending).toBe(true);
    files.deletion.show();
    await files.deletion.confirm();
    expect(remove).toHaveBeenCalledTimes(1);
    response.resolve();
    await operation;
    expect(files.node?.id).toBe(fileId);
  });

  test('renders listing independently and bounds simultaneous row eligibility checks', async (): Promise<void> => {
    const nodes = Array.from({ length: 9 }, (_, index) => filesystemNode({ id: `00000000-0000-4000-8000-${String(index + 10).padStart(12, '0')}`, kind: 'file', parent_id: folderId, name: `File ${index}` }));
    const api = new InMemoryFilesApi(rootId, [...filesystemFixture, ...nodes]);
    const files = new FilesState(api);
    const eligibility = deferred<void>();
    const check = vi.spyOn(api.filesystem, 'checkDeleteEligibility').mockReturnValue(eligibility.promise);
    await files.load(folderId);
    expect(files.phase).toBe('ready');
    expect(files.children).toHaveLength(10);
    expect(check).toHaveBeenCalledTimes(4);
    await files.load(rootId);
    eligibility.resolve();
    await Promise.resolve();
    expect(check).toHaveBeenCalledTimes(4);
    expect([...files.rowDeletion.controllers.values()].every((row) => !row.available)).toBe(true);
  });

  test('restores the invoking row on Cancel and focuses the heading after successful removal', async (): Promise<void> => {
    const { files } = fixture();
    const row = await ready(files);
    const window = new Window();
    const button = window.document.createElement('button');
    const heading = window.document.createElement('h1');
    heading.tabIndex = -1;
    window.document.body.append(button, heading);
    const detachButton = files.rowDeletion.attachButton(fileId)(button as unknown as HTMLButtonElement);
    const detachHeading = files.rowDeletion.attachFocus(heading as unknown as HTMLElement);
    row.show();
    await files.rowDeletion.cancel(fileId);
    expect(window.document.activeElement).toBe(button);
    row.show();
    await row.confirm();
    expect(window.document.activeElement).toBe(heading);
    detachButton();
    detachHeading();
  });
});
