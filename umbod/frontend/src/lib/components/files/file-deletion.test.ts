import { Window } from 'happy-dom';
import { render } from 'svelte/server';
import { describe, expect, test, vi } from 'vitest';
import { HttpError, NetworkError } from '$lib/admin/infrastructure/transport';
import { deferred, fileId, filesystemFixture, folderId, rootId } from '$lib/files/fixtures.test-support';
import { InMemoryFilesApi } from '$lib/files/infrastructure/in-memory-api.test-support';
import { FilesState } from '$lib/files/state/files-state.svelte';
import { NewFolderState } from '$lib/files/state/new-folder-state.svelte';
import { UploadState } from '$lib/files/state/upload-state.svelte';
import FileDeletionDialog from './FileDeletionDialog.svelte';
import FilesContent from './FilesContent.svelte';

function fixture(): { api: InMemoryFilesApi; files: FilesState; content: () => string } {
  const api = new InMemoryFilesApi(rootId, filesystemFixture);
  const files = new FilesState(api);
  const folder = new NewFolderState(api, files);
  const upload = new UploadState(api, files);
  return { api, files, content: (): string => render(FilesContent, { props: { state: files, folder, upload, signIn: vi.fn() } }).body };
}

describe('file deletion presentation', (): void => {
  test('shows a visible filename-labelled row action only after server eligibility succeeds', async (): Promise<void> => {
    const { api, files, content } = fixture();
    const eligibility = deferred<void>();
    vi.spyOn(api.filesystem, 'checkDeleteEligibility').mockReturnValueOnce(eligibility.promise);
    await files.load(folderId);
    expect(content()).not.toContain('row-delete');
    eligibility.resolve();
    await vi.waitFor(() => expect(files.rowDeletion.controllers.get(fileId)?.available).toBe(true));
    const window = new Window();
    window.document.body.innerHTML = content();
    expect([...window.document.querySelectorAll('th')].map((cell) => cell.textContent)).toEqual(['Name', 'Type', 'Updated', 'Actions']);
    const button = window.document.querySelector('button.row-delete');
    expect(button?.textContent?.trim()).toBe('');
    expect(button?.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true');
    expect(button?.getAttribute('aria-label')).toBe('Delete “Notes.txt”');
    expect(button?.getAttribute('title')).toBe('Delete “Notes.txt”');
    expect(button?.getAttribute('type')).toBe('button');
    expect(button?.hasAttribute('hidden')).toBe(false);
    expect(button?.closest('tr')?.textContent).toContain('Notes.txt');
  });

  test('keeps the pending icon disabled and announces deletion progress', async (): Promise<void> => {
    const { api, files, content } = fixture();
    const deletion = deferred<void>();
    vi.spyOn(api.filesystem, 'deleteFile').mockReturnValueOnce(deletion.promise);
    await files.load(folderId);
    await vi.waitFor(() => expect(files.rowDeletion.controllers.get(fileId)?.available).toBe(true));
    const controller = files.rowDeletion.controllers.get(fileId)!;
    controller.show();
    const pending = controller.confirm();
    const window = new Window();
    window.document.body.innerHTML = content();
    const button = window.document.querySelector('button.row-delete');
    expect(button?.hasAttribute('disabled')).toBe(true);
    expect(button?.getAttribute('aria-busy')).toBe('true');
    expect(button?.getAttribute('title')).toBe('Deleting…');
    expect(window.document.querySelector('[role="status"].visually-hidden')?.textContent).toBe('Deleting “Notes.txt”…');
    deletion.resolve();
    await pending;
  });

  test('never exposes root, folder or denied file row deletion', async (): Promise<void> => {
    const { api, files, content } = fixture();
    const check = vi.spyOn(api.filesystem, 'checkDeleteEligibility').mockRejectedValue(new HttpError(403, 'Forbidden', {}));
    await files.load(rootId);
    expect(check).not.toHaveBeenCalled();
    expect(content()).not.toContain('row-delete');
    await files.load(folderId);
    await vi.waitFor(() => expect(check).toHaveBeenCalledTimes(1));
    expect(content()).not.toContain('row-delete');
  });

  test('preserves the details delete action while hiding it during stalled checks', async (): Promise<void> => {
    const { api, files, content } = fixture();
    await files.load(folderId);
    expect(content()).not.toContain('Delete file');
    const eligibility = deferred<void>();
    vi.spyOn(api.filesystem, 'checkDeleteEligibility').mockReturnValueOnce(eligibility.promise);
    await files.load(fileId);
    expect(content()).not.toContain('Delete file');
    eligibility.resolve();
    await vi.waitFor(() => expect(files.deletion.available).toBe(true));
    expect(content()).toContain('Delete file');
  });

  test('retains file details and shows reload recovery when eligibility fails', async (): Promise<void> => {
    const { api, files, content } = fixture();
    vi.spyOn(api.filesystem, 'checkDeleteEligibility').mockRejectedValueOnce(new NetworkError(new Error('offline')));
    await files.load(fileId);
    await vi.waitFor(() => expect(files.deletion.needsReload).toBe(true));
    const body = content();
    expect(body).toContain('Notes.txt');
    expect(body).toContain('text/plain');
    expect(body).toContain("Couldn't check deletion availability");
    expect(body).toContain('Reload file');
    expect(body).not.toContain('Delete file');
    await files.deletion.reconcile();
    await vi.waitFor(() => expect(files.deletion.available).toBe(true));
    expect(content()).toContain('Delete file');
    expect(content()).not.toContain('Reload file');
  });

  test('shows successful deletion alongside loading and failed parent reads with only read retry', async (): Promise<void> => {
    const { api, files, content } = fixture();
    const parentListing = deferred<import('$lib/files/domain/schemas').NodeSummary[]>();
    vi.spyOn(api.filesystem, 'listChildren').mockReturnValueOnce(parentListing.promise);
    const remove = vi.spyOn(api.filesystem, 'deleteFile');
    await files.load(fileId);
    await vi.waitFor(() => expect(files.deletion.available).toBe(true));
    files.deletion.show();
    const operation = files.deletion.confirm();
    await vi.waitFor(() => expect(files.mutationNotice).toContain('was deleted'));
    await vi.waitFor(() => expect(files.phase).toBe('loading'));
    expect(content()).toContain('was deleted from the workspace.');
    expect(content()).toContain('Loading files');
    parentListing.reject(new HttpError(500, 'Unavailable', {}));
    await operation;
    const body = content();
    expect(body).toContain('was deleted from the workspace.');
    expect(body).toContain("Couldn't load files.");
    expect(body).toContain('Retry');
    expect(body).not.toContain('Delete file');
    expect(body).not.toContain("Couldn't confirm deletion");
    await files.reload();
    expect(files.phase).toBe('ready');
    expect(files.node?.id).toBe(folderId);
    expect(remove).toHaveBeenCalledTimes(1);
  });

  test('names the file in a labelled native confirmation with permanent workspace and no-restore wording', async (): Promise<void> => {
    const { files } = fixture();
    await files.load(fileId);
    await vi.waitFor(() => expect(files.deletion.available).toBe(true));
    files.deletion.show();
    const window = new Window();
    window.document.body.innerHTML = render(FileDeletionDialog, { props: { state: files.deletion } }).body;
    const dialog = window.document.querySelector('dialog');
    expect(dialog).not.toBeNull();
    expect(dialog?.hasAttribute('open')).toBe(false);
    const title = window.document.getElementById(dialog?.getAttribute('aria-labelledby') ?? '');
    const description = window.document.getElementById(dialog?.getAttribute('aria-describedby') ?? '');
    expect(title?.textContent).toBe('Delete “Notes.txt”?');
    expect(description?.textContent).toContain('permanently removes “Notes.txt” from the workspace');
    expect(description?.textContent).toContain('no restore');
    expect(description?.textContent).not.toMatch(/physical|erase|storage|disk/i);
    expect(dialog?.querySelector('[data-dialog-cancel]')?.textContent).toBe('Cancel');
    expect(dialog?.querySelector('button.danger')?.textContent).toBe('Delete file');
    expect([...window.document.querySelectorAll('button')].map((button) => button.textContent)).toEqual(['Cancel', 'Delete file']);
  });
});
