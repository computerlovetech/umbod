import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, HttpError, NetworkError, SchemaValidationError } from '$lib/admin/infrastructure/transport';
import type { FilesApi } from '../api';
import type { NodeSummary } from '../domain/schemas';
import { deferred, filesystemFixture, folderId, rootId } from '../fixtures.test-support';
import { InMemoryFilesApi } from '../infrastructure/in-memory-api';
import { FilesState } from './files-state.svelte';
import { UploadState } from './upload-state.svelte';

function fixture(): { api: FilesApi; files: FilesState; upload: UploadState } {
  const api: FilesApi = new InMemoryFilesApi(rootId, filesystemFixture);
  const files = new FilesState(api);
  return { api, files, upload: new UploadState(api, files) };
}

async function ready(files: FilesState, target: string | null = null): Promise<void> {
  await files.load(target);
  await vi.waitFor(() => expect(files.uploadAvailability).toBe('allowed'));
}

function file(name: string = 'Dropped.txt', size: number = 4): File {
  return new File(['x'.repeat(size)], name);
}

describe('page drop auto-upload', () => {
  test.each([0, 4, 8, 9000])('uploads a %s-byte file immediately with its original name and updates the listing', async (size): Promise<void> => {
    const { api, files, upload } = fixture();
    const write = vi.spyOn(api.filesystem, 'uploadFile');
    await ready(files);
    expect(upload.canDrop).toBe(true);
    const dropped = file('Original.txt', size);
    await upload.drop([dropped]);
    expect(write).toHaveBeenCalledExactlyOnceWith(rootId, { file: dropped, name: dropped.name });
    expect(files.children.filter((node) => node.name === dropped.name)).toEqual([expect.objectContaining({ kind: 'file', parent_id: rootId })]);
    expect(upload.open).toBe(false);
    expect(upload.file).toBeUndefined();
    expect(upload.pending).toBe(false);
    expect(upload.status).toBe('Original.txt uploaded.');
    expect(upload.canDrop).toBe(true);
  });

  test.each([
    { selection: [file('One.txt'), file('Two.txt')], message: /one file at a time/i },
    { selection: [], message: /choose one file/i },
    { selection: [file('bad/name')], message: /path separators/ }
  ])('invalid drop opens an error modal without writing: $message', async ({ selection, message }): Promise<void> => {
    const { api, files, upload } = fixture();
    const write = vi.spyOn(api.filesystem, 'uploadFile');
    await ready(files);
    await upload.drop(selection);
    expect(upload.open).toBe(true);
    expect(upload.error).toMatch(message);
    expect(upload.file).toBeUndefined();
    expect(upload.name).toBe('');
    expect(upload.canSubmit).toBe(false);
    expect(upload.canDrop).toBe(false);
    expect(write).not.toHaveBeenCalled();
  });

  test('transfer rejection opens the error modal and clears a stale selection without writing', async (): Promise<void> => {
    const { api, files, upload } = fixture();
    const write = vi.spyOn(api.filesystem, 'uploadFile');
    await ready(files);
    upload.show();
    upload.select([file('Past.txt')]);
    upload.changeName('Past rename.txt');
    upload.navigate();
    upload.rejectDrop('Folders cannot be uploaded.');
    expect(upload.open).toBe(true);
    expect(upload.error).toBe('Folders cannot be uploaded.');
    expect(upload.status).toBe('');
    expect(upload.file).toBeUndefined();
    expect(upload.name).toBe('');
    expect(write).not.toHaveBeenCalled();
  });

  test('a new drop replaces a previous renamed draft with the original dropped name', async (): Promise<void> => {
    const { api, files, upload } = fixture();
    const write = vi.spyOn(api.filesystem, 'uploadFile');
    await ready(files);
    upload.show();
    upload.select([file('Past.txt')]);
    upload.changeName('Past rename.txt');
    upload.cancel();
    const dropped = file('Fresh.txt');
    await upload.drop([dropped]);
    expect(write).toHaveBeenCalledExactlyOnceWith(rootId, { file: dropped, name: 'Fresh.txt' });
    expect(files.children.some((node) => node.name === 'Past rename.txt')).toBe(false);
  });

  test('server conflict retains the dropped file and modal for explicit rename', async (): Promise<void> => {
    const { api, files, upload } = fixture();
    const write = vi.spyOn(api.filesystem, 'uploadFile');
    await ready(files);
    const dropped = file('Projects');
    await upload.drop([dropped]);
    expect(write).toHaveBeenCalledExactlyOnceWith(rootId, { file: dropped, name: 'Projects' });
    expect(upload.open).toBe(true);
    expect(upload.file).toBe(dropped);
    expect(upload.name).toBe('Projects');
    expect(upload.error).toMatch(/already exists/);
    expect(upload.pending).toBe(false);
    expect(upload.uncertain).toBe(false);
    expect(upload.canDrop).toBe(false);
    expect(files.children.filter((node) => node.name === 'Projects')).toEqual([expect.objectContaining({ kind: 'directory' })]);
  });
});

describe('page drop eligibility', () => {
  test('unknown eligibility blocks drops until the authorized directory eligibility is ready', async (): Promise<void> => {
    const { api, files, upload } = fixture();
    const eligibility = deferred<void>();
    vi.spyOn(api.filesystem, 'checkUploadEligibility').mockReturnValueOnce(eligibility.promise);
    const write = vi.spyOn(api.filesystem, 'uploadFile');
    expect(upload.canDrop).toBe(false);
    await upload.drop([file()]);
    upload.rejectDrop('Ignored before loading');
    await files.load(null);
    expect(files.uploadAvailability).toBe('loading');
    expect(upload.canDrop).toBe(false);
    await upload.drop([file()]);
    upload.rejectDrop('Ignored before eligibility');
    expect(upload.open).toBe(false);
    expect(upload.error).toBe('');
    expect(write).not.toHaveBeenCalled();
    eligibility.resolve(undefined);
    await vi.waitFor(() => expect(upload.canDrop).toBe(true));
  });

  test.each([new HttpError(403, 'Forbidden', {}), new AuthenticationRequiredError(), new NetworkError('Eligibility unavailable')])('denied or failed eligibility ignores drops and rejections: %s', async (error): Promise<void> => {
    const { api, files, upload } = fixture();
    vi.spyOn(api.filesystem, 'checkUploadEligibility').mockRejectedValueOnce(error);
    const write = vi.spyOn(api.filesystem, 'uploadFile');
    await files.load(null);
    await vi.waitFor(() => expect(files.uploadAvailability).not.toBe('loading'));
    expect(upload.canDrop).toBe(false);
    await upload.drop([file()]);
    upload.rejectDrop('Ignored');
    expect(upload.open).toBe(false);
    expect(upload.error).toBe('');
    expect(write).not.toHaveBeenCalled();
  });

  test('file details ignore drops and transfer errors', async (): Promise<void> => {
    const { api, files, upload } = fixture();
    const write = vi.spyOn(api.filesystem, 'uploadFile');
    await ready(files);
    await files.load(filesystemFixture[2].id);
    expect(files.node?.kind).toBe('file');
    expect(upload.canDrop).toBe(false);
    await upload.drop([file()]);
    upload.rejectDrop('Ignored');
    expect(upload.open).toBe(false);
    expect(upload.error).toBe('');
    expect(write).not.toHaveBeenCalled();
  });

  test('an already open modal preserves its draft and error when a page drop arrives', async (): Promise<void> => {
    const { api, files, upload } = fixture();
    const write = vi.spyOn(api.filesystem, 'uploadFile');
    await ready(files);
    upload.show();
    const draft = file('Draft.txt');
    upload.select([draft]);
    upload.changeName('Rename.txt');
    upload.rejectSelection('Keep this error');
    expect(upload.canDrop).toBe(false);
    await upload.drop([file()]);
    upload.rejectDrop('Ignored');
    expect(upload.open).toBe(true);
    expect(upload.file).toBe(draft);
    expect(upload.name).toBe('Rename.txt');
    expect(upload.error).toBe('Keep this error');
    expect(write).not.toHaveBeenCalled();
  });

  test('pending parent blocks repeated drops after navigation away and back and refreshes on completion', async (): Promise<void> => {
    const { api, files, upload } = fixture();
    const commit = deferred<void>();
    const uploadFile = api.filesystem.uploadFile;
    const write = vi.spyOn(api.filesystem, 'uploadFile').mockImplementation(async (parent, input) => {
      await commit.promise;
      return uploadFile(parent, input);
    });
    const reload = vi.spyOn(files, 'reload');
    await ready(files);
    const dropped = file();
    const pending = upload.drop([dropped]);
    expect(upload.pending).toBe(true);
    expect(upload.canDrop).toBe(false);
    await upload.drop([file('Duplicate.txt')]);
    upload.navigate();
    await ready(files, folderId);
    expect(upload.canDrop).toBe(true);
    upload.navigate();
    await ready(files);
    expect(upload.open).toBe(false);
    expect(upload.pending).toBe(false);
    expect(upload.canDrop).toBe(false);
    await upload.drop([file('Duplicate.txt')]);
    upload.rejectDrop('Ignored');
    expect(upload.open).toBe(false);
    expect(write).toHaveBeenCalledTimes(1);
    expect(reload).not.toHaveBeenCalled();
    commit.resolve();
    await pending;
    expect(reload).toHaveBeenCalledTimes(1);
    expect(files.children.filter((node) => node.name === dropped.name)).toHaveLength(1);
    await vi.waitFor(() => expect(upload.canDrop).toBe(true));
  });

  test.each([new NetworkError('lost response'), new SchemaValidationError('inbound', []), new HttpError(500, 'Internal error', {})])('uncertain parent ignores drops until a successful explicit reload: %s', async (error): Promise<void> => {
    const { api, files, upload } = fixture();
    const write = vi.spyOn(api.filesystem, 'uploadFile').mockRejectedValueOnce(error);
    await ready(files);
    const dropped = file();
    await upload.drop([dropped]);
    expect(upload.uncertain).toBe(true);
    expect(upload.file).toBe(dropped);
    expect(upload.open).toBe(true);
    upload.cancel();
    expect(upload.canDrop).toBe(false);
    await upload.drop([file('Ignored.txt')]);
    upload.navigate();
    await ready(files, folderId);
    expect(upload.canDrop).toBe(true);
    upload.navigate();
    await ready(files);
    expect(upload.uncertain).toBe(false);
    expect(upload.canDrop).toBe(false);
    await upload.drop([file('Ignored.txt')]);
    upload.rejectDrop('Ignored');
    expect(upload.open).toBe(false);
    expect(write).toHaveBeenCalledTimes(1);
    vi.spyOn(api.filesystem, 'getRoot').mockRejectedValueOnce(new NetworkError('reload failed'));
    await upload.reload();
    await ready(files);
    expect(upload.canDrop).toBe(false);
    await upload.drop([file('Still ignored.txt')]);
    expect(write).toHaveBeenCalledTimes(1);
    await upload.reload();
    await vi.waitFor(() => expect(upload.canDrop).toBe(true));
    await upload.drop([file('Retry.txt')]);
    expect(write).toHaveBeenCalledTimes(2);
    expect(upload.open).toBe(false);
  });
});
