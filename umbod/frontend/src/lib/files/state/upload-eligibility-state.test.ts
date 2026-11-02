import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, HttpError, NetworkError } from '$lib/admin/infrastructure/transport';
import type { FilesApi } from '../api';
import type { NodeSummary } from '../domain/schemas';
import { deferred, fileId, filesystemFixture, filesystemNode, folderId, rootId } from '../fixtures.test-support';
import { InMemoryFilesApi } from '../infrastructure/in-memory-api.test-support';
import { FilesState } from './files-state.svelte';
import { UploadState } from './upload-state.svelte';

function fixture(): { api: FilesApi; files: FilesState; upload: UploadState } {
  const api: FilesApi = new InMemoryFilesApi(rootId, filesystemFixture);
  const files = new FilesState(api);
  return { api, files, upload: new UploadState(api, files) };
}

describe('browse upload capabilities', () => {
  test('directory capabilities allow upload while file inspection hides it', async (): Promise<void> => {
    const { api, files, upload } = fixture();
    const browse = vi.spyOn(api.filesystem, 'browse');
    await files.load(null);
    expect(files.phase).toBe('ready');
    expect(files.uploadAvailability).toBe('allowed');
    expect(upload.available).toBe(true);
    expect(browse).toHaveBeenCalledExactlyOnceWith(null, expect.any(AbortSignal));
    await files.load(fileId);
    expect(files.uploadAvailability).toBe('hidden');
    expect(upload.available).toBe(false);
  });

  test('read-only browse hides upload and reload restores the authoritative capability', async (): Promise<void> => {
    let writable = false;
    const api = new InMemoryFilesApi(rootId, filesystemFixture, undefined, undefined, undefined, () => writable);
    const files = new FilesState(api);
    const upload = new UploadState(api, files);
    await files.load(null);
    expect(files.phase).toBe('ready');
    expect(files.children.map((node) => node.id)).toEqual([folderId]);
    expect(files.uploadAvailability).toBe('denied');
    upload.show();
    expect(upload.open).toBe(false);
    writable = true;
    await files.reload();
    expect(upload.available).toBe(true);
    writable = false;
    await files.reload();
    expect(upload.available).toBe(false);
  });

  test.each([
    [new HttpError(403, 'Forbidden', {}), 'denied'],
    [new HttpError(404, 'Missing', {}), 'missing'],
    [new AuthenticationRequiredError(), 'sign-in'],
    [new NetworkError('offline'), 'error']
  ])('browse failure %s blocks upload until successful reload', async (error, phase): Promise<void> => {
    const { api, files, upload } = fixture();
    await files.load(null);
    vi.spyOn(api.filesystem, 'browse').mockRejectedValueOnce(error);
    await files.reload();
    expect(files.phase).toBe(phase);
    expect(files.uploadAvailability).toBe('hidden');
    expect(upload.available).toBe(false);
    await files.reload();
    expect(upload.available).toBe(true);
  });

  test.each(['resolve', 'reject'])('stale browse %s cannot restore upload after navigation', async (outcome): Promise<void> => {
    const { api, files, upload } = fixture();
    const response = await api.filesystem.browse(null);
    const pending = deferred<typeof response>();
    const browse = vi.spyOn(api.filesystem, 'browse').mockReturnValueOnce(pending.promise);
    const loading = files.load(null);
    const signal = browse.mock.calls[0][1];
    await files.load(fileId);
    if (outcome === 'resolve') pending.resolve(response);
    else pending.reject(new NetworkError('late'));
    await loading;
    expect(signal?.aborted).toBe(true);
    expect(files.node?.id).toBe(fileId);
    expect(files.uploadAvailability).toBe('hidden');
    expect(upload.available).toBe(false);
  });

  test.each(['resolve', 'reject'])('disposal ignores late browse %s capabilities', async (outcome): Promise<void> => {
    const { api, files, upload } = fixture();
    const response = await api.filesystem.browse(null);
    const pending = deferred<typeof response>();
    const browse = vi.spyOn(api.filesystem, 'browse').mockReturnValueOnce(pending.promise);
    const loading = files.load(null);
    const signal = browse.mock.calls[0][1];
    files.dispose();
    if (outcome === 'resolve') pending.resolve(response);
    else pending.reject(new NetworkError('late'));
    await loading;
    expect(signal?.aborted).toBe(true);
    expect(upload.available).toBe(false);
    await files.reload();
    expect(browse).toHaveBeenCalledTimes(1);
  });
});

describe('write rejection invalidates upload capability', () => {
  test.each([
    { error: new AuthenticationRequiredError(), availability: 'sign-in' },
    { error: new HttpError(403, 'Forbidden', {}), availability: 'denied' }
  ])('$availability rejection retains the draft and requires authoritative reload', async ({ error, availability }): Promise<void> => {
    const { api, files, upload } = fixture();
    await files.load(null);
    upload.show();
    const file = new File(['x'], 'Retained.txt');
    upload.select([file]);
    vi.spyOn(api.filesystem, 'uploadFile').mockRejectedValueOnce(error);
    await upload.submit();
    expect(files.uploadAvailability).toBe(availability);
    expect(files.phase).toBe('ready');
    expect(files.children.map((node) => node.id)).toEqual([folderId]);
    expect(upload.file).toBe(file);
    expect(upload.name).toBe(file.name);
    expect(upload.available).toBe(false);
    upload.changeName('Renamed.txt');
    expect(upload.canSubmit).toBe(false);
    await files.reload();
    expect(files.uploadAvailability).toBe('allowed');
  });

  test.each(['denied', 'sign-in'] as const)('rejection for another parent cannot revoke current upload: %s', async (availability): Promise<void> => {
    const { files, upload } = fixture();
    await files.load(folderId);
    files.rejectUploadAccess(rootId, availability);
    expect(files.uploadAvailability).toBe('allowed');
    expect(upload.available).toBe(true);
  });
});

describe('generic confirmed file reconciliation', () => {
  test('acceptCreated inserts and deduplicates confirmed files but rejects mismatched parents', async (): Promise<void> => {
    const { files } = fixture();
    await files.load(null);
    const target = files.creationTarget();
    if (!target) throw new Error('Expected directory target');
    const node = filesystemNode({ id: fileId, kind: 'file', parent_id: rootId, name: 'Uploaded.txt' });
    await files.acceptCreated(rootId, target.generation, node);
    await files.acceptCreated(rootId, target.generation, node);
    expect(files.children.filter((child) => child.id === fileId)).toEqual([node]);
    const before = [...files.children];
    await files.acceptCreated(rootId, target.generation, { ...node, parent_id: folderId });
    expect(files.children).toEqual(before);
  });

  test('stale generation refetches the selected parent instead of trusting stale file data', async (): Promise<void> => {
    const { api, files } = fixture();
    await files.load(null);
    const target = files.creationTarget();
    if (!target) throw new Error('Expected directory target');
    const node = await api.filesystem.uploadFile(rootId, { file: new File(['x'], 'Committed.txt'), name: 'Committed.txt' });
    await files.load(folderId);
    await files.load(null);
    const list = vi.spyOn(api.filesystem, 'listChildren');
    await files.acceptCreated(rootId, target.generation, node);
    expect(list).toHaveBeenCalledWith(rootId, expect.any(AbortSignal));
    expect(files.children.filter((child) => child.id === node.id)).toHaveLength(1);
  });

  test('confirmed file invalidates a pending stale same-parent listing', async (): Promise<void> => {
    const { api, files } = fixture();
    await files.load(null);
    const target = files.creationTarget();
    if (!target) throw new Error('Expected directory target');
    const snapshot = [...files.children];
    await files.load(folderId);
    const stale = deferred<NodeSummary[]>();
    const list = vi.spyOn(api.filesystem, 'listChildren').mockReturnValueOnce(stale.promise);
    const returning = files.load(null);
    await vi.waitFor(() => expect(list).toHaveBeenCalledTimes(1));
    const signal = list.mock.calls[0][1];
    const node = await api.filesystem.uploadFile(rootId, { file: new File(['x'], 'Committed.txt'), name: 'Committed.txt' });
    await files.acceptCreated(rootId, target.generation, node);
    expect(signal?.aborted).toBe(true);
    expect(files.children.filter((child) => child.id === node.id)).toHaveLength(1);
    stale.resolve(snapshot);
    await returning;
    expect(files.children.filter((child) => child.id === node.id)).toHaveLength(1);
  });
});
