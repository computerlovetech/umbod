import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, HttpError, NetworkError, SchemaValidationError } from '$lib/admin/infrastructure/transport';
import { deferred, fileId, filesystemFixture, filesystemNode, folderId, rootId } from '../fixtures.test-support';
import { InMemoryFilesApi } from '../infrastructure/in-memory-api';
import { FilesState } from './files-state.svelte';

function fixture(): { api: InMemoryFilesApi; files: FilesState } {
  const api = new InMemoryFilesApi(rootId, filesystemFixture);
  return { api, files: new FilesState(api) };
}

async function ready(files: FilesState): Promise<void> {
  await files.load(fileId);
  await vi.waitFor(() => expect(files.deletion.available).toBe(true));
}

describe('file deletion state', (): void => {
  test('checks file targets independently and fails closed while stalled', async (): Promise<void> => {
    const { api, files } = fixture();
    const check = vi.spyOn(api.filesystem, 'checkDeleteEligibility');
    await files.load(folderId);
    expect(check).toHaveBeenCalledExactlyOnceWith(fileId, expect.any(AbortSignal));
    const eligibility = deferred<void>();
    check.mockReturnValueOnce(eligibility.promise);
    await files.load(fileId);
    expect(files.phase).toBe('ready');
    expect(files.node?.name).toBe('Notes.txt');
    expect(files.deletion.available).toBe(false);
    files.deletion.show();
    expect(files.deletion.confirmation).toBeUndefined();
    eligibility.resolve();
    await vi.waitFor(() => expect(files.deletion.available).toBe(true));
  });

  test('captures file and revision, cancels without mutation and reloads parent after success', async (): Promise<void> => {
    const { api, files } = fixture();
    const remove = vi.spyOn(api.filesystem, 'deleteFile');
    const listing = vi.spyOn(api.filesystem, 'listChildren');
    await ready(files);
    files.deletion.show();
    expect(files.deletion.confirmation).toMatchObject({ id: fileId, name: 'Notes.txt', revision: 1 });
    files.deletion.cancel();
    await files.deletion.confirm();
    expect(remove).not.toHaveBeenCalled();
    files.deletion.show();
    await files.deletion.confirm();
    expect(remove).toHaveBeenCalledExactlyOnceWith(fileId, 1);
    expect(files.node?.id).toBe(folderId);
    expect(listing).toHaveBeenCalledWith(folderId, expect.any(AbortSignal));
    expect(files.children).toEqual([]);
  });

  test('retains successful deletion context through real parent listing failure and retry', async (): Promise<void> => {
    const { api, files } = fixture();
    const remove = vi.spyOn(api.filesystem, 'deleteFile');
    const listing = vi.spyOn(api.filesystem, 'listChildren').mockRejectedValueOnce(new HttpError(500, 'Unavailable', {}));
    await ready(files);
    files.deletion.show();
    await files.deletion.confirm();
    expect(files.phase).toBe('error');
    expect(files.mutationNotice).toBe('“Notes.txt” was deleted from the workspace.');
    expect(files.deletion.available).toBe(false);
    expect(files.deletion.message).toBe('');
    await files.reload();
    expect(listing).toHaveBeenCalledTimes(2);
    expect(files.phase).toBe('ready');
    expect(files.node?.id).toBe(folderId);
    expect(files.children).toEqual([]);
    expect(files.mutationNotice).toContain('was deleted');
    expect(remove).toHaveBeenCalledTimes(1);
  });

  test('scopes pending operations by target across navigation and concurrent deletions', async (): Promise<void> => {
    const secondId = '00000000-0000-4000-8000-000000000004';
    const api = new InMemoryFilesApi(rootId, [
      ...filesystemFixture, filesystemNode({ id: secondId, parent_id: folderId, kind: 'file', name: 'Second.txt' })
    ]);
    const files = new FilesState(api);
    const first = deferred<void>();
    const second = deferred<void>();
    const original = api.filesystem.deleteFile;
    const remove = vi.spyOn(api.filesystem, 'deleteFile').mockImplementation(async (id, revision): Promise<void> => {
      await (id === fileId ? first.promise : second.promise);
      await original(id, revision);
    });
    await ready(files);
    files.deletion.show();
    const firstOperation = files.deletion.confirm();
    expect(files.deletion.pending).toBe(true);
    await files.load(folderId);
    expect(files.deletion.pending).toBe(false);
    await ready(files);
    expect(files.deletion.pending).toBe(true);
    files.deletion.show();
    await files.deletion.confirm();
    expect(remove).toHaveBeenCalledTimes(1);
    await files.load(secondId);
    await vi.waitFor(() => expect(files.deletion.available).toBe(true));
    expect(files.deletion.pending).toBe(false);
    files.deletion.show();
    expect(files.deletion.confirmation?.id).toBe(secondId);
    const secondOperation = files.deletion.confirm();
    expect(files.deletion.pending).toBe(true);
    expect(remove).toHaveBeenCalledTimes(2);
    first.resolve();
    await firstOperation;
    expect(files.node?.id).toBe(secondId);
    expect(files.deletion.pending).toBe(true);
    expect(files.mutationNotice).toContain('Notes.txt');
    second.resolve();
    await secondOperation;
    expect(files.deletion.pending).toBe(false);
    expect(files.node?.id).toBe(folderId);
    expect(files.children).toEqual([]);
    expect(files.mutationNotice).toContain('Second.txt');
  });

  test('keeps successful deletion distinct from failed parent navigation and retries only the parent', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    const openParent = vi.fn<(id: string) => Promise<void>>().mockRejectedValueOnce(new Error('navigation failed')).mockResolvedValueOnce();
    const files = new FilesState(api, openParent);
    const remove = vi.spyOn(api.filesystem, 'deleteFile');
    await ready(files);
    files.deletion.show();
    await files.deletion.confirm();
    expect(files.deletion.mutationSucceeded).toBe(true);
    expect(files.deletion.message).toContain('File deleted.');
    expect(files.deletion.message).not.toContain("Couldn't confirm deletion");
    expect(files.deletion.available).toBe(false);
    await files.deletion.reconcile();
    expect(openParent).toHaveBeenCalledTimes(2);
    expect(remove).toHaveBeenCalledTimes(1);
  });

  test('prevents duplicate submission and never optimistically removes details', async (): Promise<void> => {
    const { api, files } = fixture();
    const response = deferred<void>();
    const remove = vi.spyOn(api.filesystem, 'deleteFile').mockReturnValue(response.promise);
    await ready(files);
    files.deletion.show();
    const operation = files.deletion.confirm();
    await files.deletion.confirm();
    files.deletion.show();
    expect(files.deletion.confirmation).toBeUndefined();
    expect(files.node?.id).toBe(fileId);
    expect(files.deletion.pending).toBe(true);
    expect(remove).toHaveBeenCalledTimes(1);
    response.resolve();
    await operation;
  });

  test.each([new HttpError(403, 'Forbidden', {}), new Error('offline'), new AuthenticationRequiredError()])('hides deletion on failed eligibility %s', async (error): Promise<void> => {
    const { api, files } = fixture();
    vi.spyOn(api.filesystem, 'checkDeleteEligibility').mockRejectedValue(error);
    await files.load(fileId);
    await Promise.resolve();
    expect(files.phase).toBe('ready');
    expect(files.deletion.available).toBe(false);
    files.deletion.show();
    expect(files.deletion.confirmation).toBeUndefined();
  });

  test.each([
    new NetworkError(new Error('offline')),
    new HttpError(500, 'Server error', {}),
    new SchemaValidationError('inbound', [])
  ])('keeps details visible and recovers failed eligibility after reload %s', async (error): Promise<void> => {
    const { api, files } = fixture();
    const check = vi.spyOn(api.filesystem, 'checkDeleteEligibility').mockRejectedValueOnce(error);
    await files.load(fileId);
    await vi.waitFor(() => expect(files.deletion.needsReload).toBe(true));
    expect(files.phase).toBe('ready');
    expect(files.node?.name).toBe('Notes.txt');
    expect(files.deletion.available).toBe(false);
    expect(files.deletion.signInRequired).toBe(false);
    expect(files.deletion.message).toContain("Couldn't check deletion availability");
    await files.deletion.reconcile();
    await vi.waitFor(() => expect(files.deletion.available).toBe(true));
    expect(check).toHaveBeenCalledTimes(2);
    expect(files.deletion.message).toBe('');
    expect(files.deletion.needsReload).toBe(false);
  });

  test.each([403, 409, 404])('quietly hides denied eligibility %s', async (status): Promise<void> => {
    const { api, files } = fixture();
    vi.spyOn(api.filesystem, 'checkDeleteEligibility').mockRejectedValueOnce(new HttpError(status, 'Unavailable', {}));
    await files.load(fileId);
    await Promise.resolve();
    expect(files.deletion.available).toBe(false);
    expect(files.deletion.message).toBe('');
    expect(files.deletion.needsReload).toBe(false);
    expect(files.deletion.signInRequired).toBe(false);
  });

  test('keeps eligibility authentication distinct from recoverable service failures', async (): Promise<void> => {
    const { api, files } = fixture();
    vi.spyOn(api.filesystem, 'checkDeleteEligibility').mockRejectedValueOnce(new AuthenticationRequiredError());
    await files.load(fileId);
    await vi.waitFor(() => expect(files.deletion.signInRequired).toBe(true));
    expect(files.deletion.available).toBe(false);
    expect(files.deletion.message).toBe('');
    expect(files.deletion.needsReload).toBe(false);
  });

  test.each([
    [new HttpError(412, 'Stale', {}), 'changed'],
    [new HttpError(403, 'Forbidden', {}), 'permission'],
    [new AuthenticationRequiredError(), 'Sign in'],
    [new NetworkError(new Error('offline')), "Couldn't confirm deletion"]
  ])('requires reconciliation instead of retry after %s', async (error, message): Promise<void> => {
    const { api, files } = fixture();
    const remove = vi.spyOn(api.filesystem, 'deleteFile').mockRejectedValueOnce(error);
    await ready(files);
    files.deletion.show();
    await files.deletion.confirm();
    expect(files.deletion.message).toContain(message);
    expect(files.deletion.available).toBe(false);
    expect(files.deletion.needsReload).toBe(true);
    files.deletion.show();
    await files.deletion.confirm();
    expect(remove).toHaveBeenCalledTimes(1);
    await files.deletion.reconcile();
    await vi.waitFor(() => expect(files.deletion.available).toBe(true));
    expect(files.deletion.confirmation).toBeUndefined();
  });

  test('reconciles a lost successful response as an unavailable file, not another delete', async (): Promise<void> => {
    const { api, files } = fixture();
    const original = api.filesystem.deleteFile;
    const remove = vi.spyOn(api.filesystem, 'deleteFile').mockImplementation(async (id, revision): Promise<void> => {
      await original(id, revision);
      throw new NetworkError(new Error('lost response'));
    });
    await ready(files);
    files.deletion.show();
    await files.deletion.confirm();
    await files.deletion.reconcile();
    expect(files.phase).toBe('missing');
    expect(files.deletion.available).toBe(false);
    expect(remove).toHaveBeenCalledTimes(1);
  });

  test.each(['navigate', 'dispose'])('ignores late eligibility and mutation responses after %s', async (action): Promise<void> => {
    const { api, files } = fixture();
    const eligibility = deferred<void>();
    vi.spyOn(api.filesystem, 'checkDeleteEligibility').mockReturnValueOnce(eligibility.promise);
    await files.load(fileId);
    if (action === 'dispose') files.dispose();
    else await files.load(folderId);
    eligibility.resolve();
    await Promise.resolve();
    expect(files.deletion.available).toBe(false);
    const second = fixture();
    const response = deferred<void>();
    vi.spyOn(second.api.filesystem, 'deleteFile').mockReturnValueOnce(response.promise);
    await ready(second.files);
    second.files.deletion.show();
    const operation = second.files.deletion.confirm();
    if (action === 'dispose') second.files.dispose();
    else await second.files.load(rootId);
    response.resolve();
    await operation;
    expect(second.files.node?.id).toBe(action === 'dispose' ? fileId : rootId);
    expect(second.files.deletion.confirmation).toBeUndefined();
    expect(second.files.deletion.message).toBe('');
  });
});
