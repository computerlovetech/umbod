import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, HttpError, NetworkError, SchemaValidationError } from '$lib/admin/infrastructure/transport';
import { UploadPhaseError } from '../errors';
import type { FilesApi } from '../api';
import type { NodeSummary } from '../domain/schemas';
import { deferred, filesystemFixture, filesystemNode, folderId, rootId } from '../fixtures.test-support';
import { InMemoryFilesApi } from '../infrastructure/in-memory-api.test-support';
import { FilesState } from './files-state.svelte';
import { UploadState } from './upload-state.svelte';

function fixture(): { api: FilesApi; files: FilesState; upload: UploadState } {
  const api: FilesApi = new InMemoryFilesApi(rootId, filesystemFixture);
  const files = new FilesState(api);
  return { api, files, upload: new UploadState(api, files) };
}

async function openUpload(files: FilesState, upload: UploadState, target: string | null = null): Promise<void> {
  await files.load(target);
  await vi.waitFor(() => expect(files.uploadAvailability).toBe('allowed'));
  upload.show();
}

function selectedFile(name: string = 'Draft.txt', size: number = 4): File {
  return new File(['x'.repeat(size)], name, { type: 'text/plain' });
}

describe('upload selection and validation', () => {
  test('requires loaded eligibility and a directory before opening or submitting', async (): Promise<void> => {
    const { api, files, upload } = fixture();
    const eligibility = deferred<void>();
    vi.spyOn(api.filesystem, 'checkUploadEligibility').mockReturnValueOnce(eligibility.promise);
    const write = vi.spyOn(api.filesystem, 'uploadFile');
    upload.show();
    expect(upload.open).toBe(false);
    await files.load(null);
    upload.show();
    expect(upload.available).toBe(false);
    expect(upload.open).toBe(false);
    expect(upload.canSubmit).toBe(false);
    eligibility.resolve(undefined);
    await vi.waitFor(() => expect(upload.available).toBe(true));
    upload.show();
    upload.select([selectedFile()]);
    expect(upload.canSubmit).toBe(true);
    upload.navigate();
    await files.load(filesystemFixture[2].id);
    upload.show();
    await upload.submit();
    expect(upload.open).toBe(false);
    expect(upload.available).toBe(false);
    expect(write).not.toHaveBeenCalled();
  });

  test.each([0, 8, 9000])('shared picker/drop selection accepts %s bytes without a client size limit', async (size): Promise<void> => {
    const { api, files, upload } = fixture();
    await openUpload(files, upload);
    const file = selectedFile('Empty or full.txt', size);
    upload.select([file]);
    expect(upload.file).toBe(file);
    expect(upload.name).toBe(file.name);
    expect(upload.status).toContain('Ready to upload');
    expect(upload.canSubmit).toBe(true);
    const write = vi.spyOn(api.filesystem, 'uploadFile');
    await upload.submit();
    expect(write).toHaveBeenCalledWith(rootId, { file, name: file.name });
  });

  test('multiple and invalid-name selections preserve the previous safe file and name', async (): Promise<void> => {
    const { files, upload } = fixture();
    await openUpload(files, upload);
    const file = selectedFile();
    upload.select([file]);
    upload.changeName('Keep.txt');
    upload.select([selectedFile('One.txt'), selectedFile('Two.txt')]);
    expect(upload.error).toMatch(/one file/i);
    expect(upload.file).toBe(file);
    expect(upload.name).toBe('Keep.txt');
    upload.select([selectedFile('bad/name')]);
    expect(upload.error).toMatch(/path separators/);
    expect(upload.file).toBe(file);
    expect(upload.name).toBe('Keep.txt');
    upload.select([]);
    expect(upload.file).toBe(file);
    upload.select([selectedFile('Replacement.txt')]);
    expect(upload.error).toBe('');
    expect(upload.canSubmit).toBe(true);
    upload.remove();
    expect(upload.file).toBeUndefined();
    expect(upload.name).toBe('');
    expect(upload.canSubmit).toBe(false);
  });

  test.each(['', ' ', '.', '..', '../bad', 'bad\\name', 'bad\u0000name'])('invalid rename %j cannot write', async (name): Promise<void> => {
    const { api, files, upload } = fixture();
    const write = vi.spyOn(api.filesystem, 'uploadFile');
    await openUpload(files, upload);
    const file = selectedFile();
    upload.select([file]);
    upload.changeName(name);
    expect(upload.canSubmit).toBe(false);
    await upload.submit();
    expect(write).not.toHaveBeenCalled();
    expect(upload.file).toBe(file);
    upload.changeName('Renamed.txt');
    expect(upload.canSubmit).toBe(true);
  });
});

describe('confirmed and rejected uploads', () => {
  test('success inserts a generic file once, closes the form and announces completion', async (): Promise<void> => {
    const { api, files, upload } = fixture();
    const write = vi.spyOn(api.filesystem, 'uploadFile');
    await openUpload(files, upload);
    upload.select([selectedFile()]);
    upload.changeName('Confirmed.txt');
    await upload.submit();
    expect(files.children.filter((node) => node.name === 'Confirmed.txt')).toEqual([expect.objectContaining({ kind: 'file', parent_id: rootId })]);
    expect(upload.open).toBe(false);
    expect(upload.file).toBeUndefined();
    expect(upload.name).toBe('');
    expect(upload.pending).toBe(false);
    expect(upload.status).toBe('Confirmed.txt uploaded.');
    await upload.submit();
    expect(write).toHaveBeenCalledTimes(1);
  });

  test('409 retains file and name and permits explicit retry after renaming without overwriting', async (): Promise<void> => {
    const { api, files, upload } = fixture();
    const write = vi.spyOn(api.filesystem, 'uploadFile');
    await openUpload(files, upload);
    const file = selectedFile('Projects');
    upload.select([file]);
    await upload.submit();
    expect(upload.error).toMatch(/already exists/);
    expect(upload.open).toBe(true);
    expect(upload.file).toBe(file);
    expect(upload.name).toBe('Projects');
    expect(upload.uncertain).toBe(false);
    expect(write).toHaveBeenCalledTimes(1);
    upload.changeName('Unique.txt');
    await upload.submit();
    expect(write).toHaveBeenCalledTimes(2);
    expect(files.children.some((node) => node.name === 'Projects' && node.kind === 'directory')).toBe(true);
    expect(files.children.some((node) => node.name === 'Unique.txt' && node.kind === 'file')).toBe(true);
  });

  test('413 requests a smaller file and allows replacement selection', async (): Promise<void> => {
    const { api, files, upload } = fixture();
    const write = vi.spyOn(api.filesystem, 'uploadFile').mockRejectedValueOnce(new HttpError(413, 'Too large', {}));
    await openUpload(files, upload);
    const file = selectedFile();
    upload.select([file]);
    upload.changeName('Keep renamed.txt');
    await upload.submit();
    expect(upload.error).toMatch(/smaller file/);
    expect(upload.name).toBe('Keep renamed.txt');
    expect(upload.file).toBe(file);
    expect(upload.uncertain).toBe(false);
    expect(files.uploadAvailability).toBe('allowed');
    expect(write).toHaveBeenCalledTimes(1);
    upload.select([selectedFile('Smaller.txt', 1)]);
    await upload.submit();
    expect(upload.open).toBe(false);
    expect(write).toHaveBeenCalledTimes(2);
  });

  test.each([
    [new AuthenticationRequiredError(), /sign in/i],
    [new HttpError(403, 'Forbidden', {}), /can't upload/]
  ])('authentication and authorization rejection retain selection safely: %s', async (error, message): Promise<void> => {
    const { api, files, upload } = fixture();
    const write = vi.spyOn(api.filesystem, 'uploadFile').mockRejectedValueOnce(error);
    await openUpload(files, upload);
    const before = [...files.children];
    const file = selectedFile();
    upload.select([file]);
    await upload.submit();
    expect(upload.error).toMatch(message);
    expect(upload.file).toBe(file);
    expect(upload.name).toBe(file.name);
    expect(upload.open).toBe(true);
    expect(upload.pending).toBe(false);
    expect(upload.uncertain).toBe(false);
    expect(files.children).toEqual(before);
    expect(write).toHaveBeenCalledTimes(1);
    expect(upload.signInRequired).toBe(error instanceof AuthenticationRequiredError);
    expect(files.uploadAvailability).toBe(error instanceof AuthenticationRequiredError ? 'sign-in' : 'denied');
    expect(upload.available).toBe(false);
    expect(upload.canSubmit).toBe(false);
    upload.changeName('Renamed after denial.txt');
    expect(upload.error).toBe('');
    expect(upload.file).toBe(file);
    expect(upload.available).toBe(false);
    expect(upload.canSubmit).toBe(false);
    upload.show();
    await upload.submit();
    expect(write).toHaveBeenCalledTimes(1);
    if (!(error instanceof AuthenticationRequiredError)) {
      await files.checkUploadAvailability();
      expect(upload.available).toBe(true);
      expect(upload.canSubmit).toBe(true);
      await upload.submit();
      expect(write).toHaveBeenCalledTimes(2);
      expect(upload.open).toBe(false);
    } else {
      await files.checkUploadAvailability();
      expect(upload.signInRequired).toBe(true);
      expect(upload.canSubmit).toBe(false);
      await upload.submit();
      expect(write).toHaveBeenCalledTimes(1);
    }
  });

  test.each([new AuthenticationRequiredError(), new HttpError(403, 'Forbidden', {})])('denied upload cannot reopen or regain availability by cancelling: %s', async (error): Promise<void> => {
    const { api, files, upload } = fixture();
    const write = vi.spyOn(api.filesystem, 'uploadFile').mockRejectedValueOnce(error);
    await openUpload(files, upload);
    upload.select([selectedFile()]);
    await upload.submit();
    upload.cancel();
    upload.show();
    expect(upload.open).toBe(false);
    expect(upload.available).toBe(false);
    expect(upload.canSubmit).toBe(false);
    await upload.submit();
    expect(write).toHaveBeenCalledTimes(1);
  });

  test.each([new AuthenticationRequiredError(), new HttpError(403, 'Forbidden', {})])('late denial in another parent cannot invalidate current permission or draft: %s', async (error): Promise<void> => {
    const { api, files, upload } = fixture();
    const response = deferred<NodeSummary>();
    vi.spyOn(api.filesystem, 'uploadFile').mockReturnValueOnce(response.promise);
    await openUpload(files, upload);
    upload.select([selectedFile('Old.txt')]);
    const pending = upload.submit();
    upload.navigate();
    await openUpload(files, upload, folderId);
    const file = selectedFile('Current.txt');
    upload.select([file]);
    response.reject(error);
    await pending;
    expect(files.uploadAvailability).toBe('allowed');
    expect(upload.available).toBe(true);
    expect(upload.canSubmit).toBe(true);
    expect(upload.signInRequired).toBe(false);
    expect(upload.file).toBe(file);
    expect(upload.name).toBe(file.name);
    expect(upload.error).toBe('');
  });
});

describe('phase-aware upload recovery', () => {
  test.each(['begin', 'transfer'] as const)('%s failure retains selection and permits immediate retry without reload', async (phase): Promise<void> => {
    const { api, files, upload } = fixture();
    const write = vi.spyOn(api.filesystem, 'uploadFile');
    vi.spyOn(api.filesystem, phase === 'begin' ? 'beginUpload' : 'transferUpload').mockRejectedValueOnce(new NetworkError('lost response'));
    const complete = vi.spyOn(api.filesystem, 'completeUpload');
    await openUpload(files, upload);
    const reload = vi.spyOn(files, 'reload');
    const file = selectedFile();
    upload.select([file]);
    await upload.submit();
    expect(upload.file).toBe(file);
    expect(upload.uncertain).toBe(false);
    expect(upload.canSubmit).toBe(true);
    expect(upload.error).not.toMatch(/reload|confirm/i);
    expect(complete).not.toHaveBeenCalled();
    await upload.submit();
    expect(complete).toHaveBeenCalledTimes(1);
    expect(write).toHaveBeenCalledTimes(2);
    expect(reload).not.toHaveBeenCalled();
    expect(upload.open).toBe(false);
  });

  test('lost completion response remains uncertain and blocks retries', async (): Promise<void> => {
    const { api, files, upload } = fixture();
    const write = vi.spyOn(api.filesystem, 'uploadFile');
    vi.spyOn(api.filesystem, 'completeUpload').mockRejectedValueOnce(new NetworkError('lost completion'));
    await openUpload(files, upload);
    upload.select([selectedFile()]);
    await upload.submit();
    expect(upload.uncertain).toBe(true);
    expect(upload.canSubmit).toBe(false);
    expect(upload.error).toMatch(/confirm.*reload/i);
    await upload.submit();
    expect(write).toHaveBeenCalledTimes(1);
  });

  test.each(['begin', 'transfer', 'complete'] as const)('expired %s session is recoverable without folder reload', async (phase): Promise<void> => {
    const { api, files, upload } = fixture();
    vi.spyOn(api.filesystem, 'uploadFile').mockRejectedValueOnce(new UploadPhaseError(phase, new HttpError(410, 'Gone', { detail: { code: 'filesystem_upload_expired' } })));
    await openUpload(files, upload);
    upload.select([selectedFile()]);
    await upload.submit();
    expect(upload.error).toMatch(/expired/);
    expect(upload.uncertain).toBe(false);
    expect(upload.canSubmit).toBe(true);
    await upload.submit();
    expect(upload.open).toBe(false);
  });

  test.each([
    { code: 'filesystem_upload_conflict', message: /session.*ready/i, retryable: true },
    { code: 'filesystem_wrong_node_kind', message: /folder.*destination/i, retryable: false },
    { code: 'unknown_conflict', message: /session.*ready/i, retryable: true }
  ])('409 $code is not a filename collision', async ({ code, message, retryable }): Promise<void> => {
    const { api, files, upload } = fixture();
    vi.spyOn(api.filesystem, 'uploadFile').mockRejectedValueOnce(new UploadPhaseError('begin', new HttpError(409, 'Conflict', { detail: { code } })));
    await openUpload(files, upload);
    upload.select([selectedFile()]);
    await upload.submit();
    expect(upload.error).toMatch(message);
    expect(upload.error).not.toMatch(/already exists/);
    expect(upload.uncertain).toBe(false);
    expect(upload.canSubmit).toBe(retryable);
  });

  test.each([
    { cause: new AuthenticationRequiredError(), availability: 'sign-in' },
    { cause: new HttpError(403, 'Forbidden', {}), availability: 'denied' }
  ])('wrapped authentication failure preserves $availability state', async ({ cause, availability }): Promise<void> => {
    const { api, files, upload } = fixture();
    vi.spyOn(api.filesystem, 'uploadFile').mockRejectedValueOnce(new UploadPhaseError('transfer', cause));
    await openUpload(files, upload);
    upload.select([selectedFile()]);
    await upload.submit();
    expect(files.uploadAvailability).toBe(availability);
    expect(upload.signInRequired).toBe(cause instanceof AuthenticationRequiredError);
    expect(upload.canSubmit).toBe(false);
    expect(upload.uncertain).toBe(false);
  });
});

describe('pending and uncertain upload lifetimes', () => {
  test('pending upload locks duplicate submit, selection, rename, removal and cancellation', async (): Promise<void> => {
    const { api, files, upload } = fixture();
    const result = deferred<NodeSummary>();
    const write = vi.spyOn(api.filesystem, 'uploadFile').mockReturnValueOnce(result.promise);
    await openUpload(files, upload);
    const file = selectedFile();
    upload.select([file]);
    const pending = upload.submit();
    upload.select([selectedFile('Ignored.txt')]);
    upload.changeName('Ignored.txt');
    upload.remove();
    upload.cancel();
    upload.rejectSelection('Ignored');
    await upload.reload();
    await upload.submit();
    expect(upload.pending).toBe(true);
    expect(upload.canSubmit).toBe(false);
    expect(upload.open).toBe(true);
    expect(upload.file).toBe(file);
    expect(upload.name).toBe(file.name);
    expect(upload.error).toBe('');
    expect(write).toHaveBeenCalledTimes(1);
    result.resolve(filesystemNode({ kind: 'file', parent_id: rootId, name: file.name }));
    await pending;
    expect(upload.pending).toBe(false);
  });

  test.each([null, folderId])('navigation away and back to %s preserves the pending lock and reconciles once', async (target): Promise<void> => {
    const { api, files, upload } = fixture();
    const commit = deferred<void>();
    const uploadFile = api.filesystem.uploadFile;
    const write = vi.spyOn(api.filesystem, 'uploadFile').mockImplementation(async (parent, input) => {
      await commit.promise;
      return uploadFile(parent, input);
    });
    await openUpload(files, upload, target);
    const file = selectedFile();
    upload.select([file]);
    const pending = upload.submit();
    upload.navigate();
    await files.load(target === null ? folderId : null);
    upload.navigate();
    await openUpload(files, upload, target);
    expect(upload.pending).toBe(true);
    expect(upload.file).toBe(file);
    expect(upload.name).toBe(file.name);
    await upload.submit();
    expect(write).toHaveBeenCalledTimes(1);
    commit.resolve();
    await pending;
    expect(files.node?.id).toBe(target ?? rootId);
    expect(files.children.filter((node) => node.name === file.name)).toHaveLength(1);
    expect(upload.pending).toBe(false);
    expect(upload.open).toBe(false);
  });

  test('late response cannot pollute another directory or clear its draft', async (): Promise<void> => {
    const { api, files, upload } = fixture();
    const result = deferred<NodeSummary>();
    vi.spyOn(api.filesystem, 'uploadFile').mockReturnValueOnce(result.promise);
    await openUpload(files, upload);
    upload.select([selectedFile('Old.txt')]);
    const pending = upload.submit();
    upload.navigate();
    await openUpload(files, upload, folderId);
    const draft = selectedFile('New.txt');
    upload.select([draft]);
    result.resolve(filesystemNode({ kind: 'file', parent_id: rootId, name: 'Old.txt' }));
    await pending;
    expect(files.children.map((node) => node.name)).toEqual(['Notes.txt']);
    expect(upload.file).toBe(draft);
    expect(upload.name).toBe('New.txt');
    expect(upload.open).toBe(true);
    expect(upload.status).toContain('New.txt selected');
  });

  test.each([
    new NetworkError('lost response'),
    new SchemaValidationError('inbound', []),
    new HttpError(500, 'Internal error', {})
  ])('unknown outcome blocks retries across cancel and navigation until successful explicit reload: %s', async (error): Promise<void> => {
    const { api, files, upload } = fixture();
    const write = vi.spyOn(api.filesystem, 'uploadFile').mockRejectedValueOnce(error);
    await openUpload(files, upload);
    const file = selectedFile();
    upload.select([file]);
    await upload.submit();
    expect(upload.uncertain).toBe(true);
    expect(upload.error).toMatch(/confirm the upload/);
    expect(upload.file).toBe(file);
    expect(upload.canSubmit).toBe(false);
    upload.select([selectedFile('Ignored.txt')]);
    upload.changeName('Ignored.txt');
    upload.remove();
    expect(upload.file).toBe(file);
    expect(upload.name).toBe(file.name);
    await upload.submit();
    upload.cancel();
    upload.show();
    expect(upload.uncertain).toBe(true);
    await upload.submit();
    upload.navigate();
    await files.load(folderId);
    upload.navigate();
    await openUpload(files, upload);
    expect(upload.uncertain).toBe(true);
    await upload.submit();
    expect(write).toHaveBeenCalledTimes(1);
    vi.spyOn(api.filesystem, 'getRoot').mockRejectedValueOnce(new NetworkError('reload failed'));
    await upload.reload();
    expect(files.phase).toBe('error');
    await openUpload(files, upload);
    expect(upload.uncertain).toBe(true);
    await upload.submit();
    expect(write).toHaveBeenCalledTimes(1);
    await upload.reload();
    await vi.waitFor(() => expect(files.uploadAvailability).toBe('allowed'));
    upload.show();
    expect(upload.uncertain).toBe(false);
    upload.select([selectedFile('Explicit retry.txt')]);
    await upload.submit();
    expect(write).toHaveBeenCalledTimes(2);
    expect(upload.open).toBe(false);
  });

  test.each(['parent', 'name', 'kind'])('mismatched successful response %s is uncertain and never inserted', async (mismatch): Promise<void> => {
    const { api, files, upload } = fixture();
    const node = filesystemNode({ kind: mismatch === 'kind' ? 'directory' : 'file', parent_id: mismatch === 'parent' ? folderId : rootId, name: mismatch === 'name' ? 'Wrong.txt' : 'Draft.txt' });
    const write = vi.spyOn(api.filesystem, 'uploadFile').mockResolvedValueOnce(node);
    await openUpload(files, upload);
    const before = [...files.children];
    upload.select([selectedFile()]);
    await upload.submit();
    expect(upload.uncertain).toBe(true);
    expect(files.children).toEqual(before);
    await upload.submit();
    expect(write).toHaveBeenCalledTimes(1);
  });

  test.each(['resolve', 'reject'])('disposal ignores a late upload %s', async (outcome): Promise<void> => {
    const { api, files, upload } = fixture();
    const result = deferred<NodeSummary>();
    const write = vi.spyOn(api.filesystem, 'uploadFile').mockReturnValueOnce(result.promise);
    await openUpload(files, upload);
    const before = [...files.children];
    upload.select([selectedFile()]);
    const pending = upload.submit();
    upload.dispose();
    if (outcome === 'resolve') result.resolve(filesystemNode({ kind: 'file', parent_id: rootId, name: 'Draft.txt' }));
    else result.reject(new NetworkError('late failure'));
    await pending;
    upload.show();
    await upload.submit();
    expect(upload.open).toBe(false);
    expect(upload.file).toBeUndefined();
    expect(upload.error).toBe('');
    expect(upload.status).toBe('');
    expect(files.children).toEqual(before);
    expect(write).toHaveBeenCalledTimes(1);
  });
});
