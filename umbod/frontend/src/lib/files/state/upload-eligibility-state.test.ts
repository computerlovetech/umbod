import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, HttpError, NetworkError } from '$lib/admin/infrastructure/transport';
import type { FilesApi } from '../api';
import type { NodeSummary } from '../domain/schemas';
import { deferred, fileId, filesystemFixture, filesystemNode, folderId, rootId } from '../fixtures.test-support';
import { InMemoryFilesApi } from '../infrastructure/in-memory-api';
import { FilesState } from './files-state.svelte';
import { UploadState } from './upload-state.svelte';

function fixture(): { api: FilesApi; files: FilesState; upload: UploadState } {
  const api: FilesApi = new InMemoryFilesApi(rootId, filesystemFixture);
  const files = new FilesState(api);
  return { api, files, upload: new UploadState(api, files) };
}

describe('directory upload eligibility', () => {
  test('directory browsing is ready while eligibility is pending and files never request eligibility', async (): Promise<void> => {
    const { api, files, upload } = fixture();
    const pending = deferred<void>();
    const eligibility = vi.spyOn(api.filesystem, 'checkUploadEligibility').mockReturnValueOnce(pending.promise);
    await files.load(null);
    expect(files.phase).toBe('ready');
    expect(files.children.map((node) => node.id)).toEqual([folderId]);
    expect(files.uploadAvailability).toBe('loading');
    expect(upload.available).toBe(false);
    expect(eligibility).toHaveBeenCalledWith(rootId, expect.any(AbortSignal));
    pending.resolve(undefined);
    await vi.waitFor(() => expect(files.uploadAvailability).toBe('allowed'));
    await files.load(fileId);
    expect(files.phase).toBe('ready');
    expect(files.uploadAvailability).toBe('hidden');
    expect(eligibility).toHaveBeenCalledTimes(1);
  });

  test.each([
    [new HttpError(403, 'Forbidden', {}), 'denied'],
    [new HttpError(404, 'Missing', {}), 'denied'],
    [new AuthenticationRequiredError(), 'sign-in'],
    [new NetworkError('offline'), 'error'],
    [new HttpError(500, 'Failed', {}), 'error']
  ])('eligibility failure %s hides upload without blocking browsing and explicit retry recovers', async (error, availability): Promise<void> => {
    const { api, files, upload } = fixture();
    const eligibility = vi.spyOn(api.filesystem, 'checkUploadEligibility').mockRejectedValueOnce(error);
    await files.load(null);
    await vi.waitFor(() => expect(files.uploadAvailability).toBe(availability));
    expect(files.phase).toBe('ready');
    expect(files.node?.id).toBe(rootId);
    expect(files.children.map((node) => node.id)).toEqual([folderId]);
    upload.show();
    expect(upload.open).toBe(false);
    expect(upload.available).toBe(false);
    expect(eligibility).toHaveBeenCalledTimes(1);
    await files.checkUploadAvailability();
    expect(files.uploadAvailability).toBe('allowed');
  });

  test.each(['resolve', 'reject'])('stale eligibility %s cannot enable upload or replace eligibility for another parent', async (outcome): Promise<void> => {
    const { api, files, upload } = fixture();
    const old = deferred<void>();
    const current = deferred<void>();
    const eligibility = vi.spyOn(api.filesystem, 'checkUploadEligibility').mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
    await files.load(null);
    const oldSignal = eligibility.mock.calls[0][1];
    await files.load(folderId);
    expect(oldSignal?.aborted).toBe(true);
    expect(files.uploadAvailability).toBe('loading');
    if (outcome === 'resolve') old.resolve(undefined);
    else old.reject(new HttpError(403, 'Forbidden', {}));
    await old.promise.catch(() => undefined);
    expect(files.node?.id).toBe(folderId);
    expect(files.uploadAvailability).toBe('loading');
    upload.show();
    expect(upload.open).toBe(false);
    current.resolve(undefined);
    await vi.waitFor(() => expect(files.uploadAvailability).toBe('allowed'));
  });

  test('later eligibility check wins within the same directory', async (): Promise<void> => {
    const { api, files } = fixture();
    const old = deferred<void>();
    vi.spyOn(api.filesystem, 'checkUploadEligibility').mockReturnValueOnce(old.promise).mockResolvedValueOnce(undefined);
    await files.load(null);
    await files.checkUploadAvailability();
    old.resolve(undefined);
    await old.promise;
    expect(files.uploadAvailability).toBe('allowed');
  });

  test.each(['resolve', 'reject'])('disposal aborts and ignores late eligibility %s', async (outcome): Promise<void> => {
    const { api, files } = fixture();
    const pending = deferred<void>();
    const eligibility = vi.spyOn(api.filesystem, 'checkUploadEligibility').mockReturnValueOnce(pending.promise);
    await files.load(null);
    const signal = eligibility.mock.calls[0][1];
    files.dispose();
    if (outcome === 'resolve') pending.resolve(undefined);
    else pending.reject(new NetworkError('late'));
    await pending.promise.catch(() => undefined);
    expect(signal?.aborted).toBe(true);
    expect(files.uploadAvailability).not.toBe('allowed');
    await files.checkUploadAvailability();
    expect(eligibility).toHaveBeenCalledTimes(1);
  });
});

describe('write rejection invalidates upload eligibility', () => {
  test.each([
    { error: new AuthenticationRequiredError(), availability: 'sign-in' },
    { error: new HttpError(403, 'Forbidden', {}), availability: 'denied' }
  ])('$availability upload rejection invalidates an outstanding successful eligibility response', async ({ error, availability }): Promise<void> => {
    const { api, files, upload } = fixture();
    await files.load(null);
    await vi.waitFor(() => expect(upload.available).toBe(true));
    upload.show();
    const file = new File(['x'], 'Retained.txt');
    upload.select([file]);
    const response = deferred<NodeSummary>();
    vi.spyOn(api.filesystem, 'uploadFile').mockReturnValueOnce(response.promise);
    const pending = upload.submit();
    const eligibility = deferred<void>();
    vi.spyOn(api.filesystem, 'checkUploadEligibility').mockReturnValueOnce(eligibility.promise);
    const checking = files.checkUploadAvailability();
    response.reject(error);
    await pending;
    expect(files.uploadAvailability).toBe(availability);
    expect(files.phase).toBe('ready');
    expect(files.children.map((node) => node.id)).toEqual([folderId]);
    expect(upload.file).toBe(file);
    expect(upload.name).toBe(file.name);
    expect(upload.available).toBe(false);
    eligibility.resolve(undefined);
    await checking;
    expect(files.uploadAvailability).toBe(availability);
    expect(upload.available).toBe(false);
    upload.changeName('Renamed.txt');
    expect(upload.canSubmit).toBe(false);
    await files.checkUploadAvailability();
    expect(files.uploadAvailability).toBe('allowed');
  });

  test.each(['denied', 'sign-in'] as const)('rejectUploadAccess for another parent cannot invalidate the current allowed or pending eligibility: %s', async (availability): Promise<void> => {
    const { api, files, upload } = fixture();
    await files.load(folderId);
    await vi.waitFor(() => expect(upload.available).toBe(true));
    files.rejectUploadAccess(rootId, availability);
    expect(files.uploadAvailability).toBe('allowed');
    const eligibility = deferred<void>();
    vi.spyOn(api.filesystem, 'checkUploadEligibility').mockReturnValueOnce(eligibility.promise);
    const checking = files.checkUploadAvailability();
    files.rejectUploadAccess(rootId, availability);
    expect(files.uploadAvailability).toBe('loading');
    eligibility.resolve(undefined);
    await checking;
    expect(files.uploadAvailability).toBe('allowed');
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
