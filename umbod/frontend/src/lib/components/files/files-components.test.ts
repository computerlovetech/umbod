import { Window } from 'happy-dom';
import { render } from 'svelte/server';
import { describe, expect, test, vi } from 'vitest';
import { HttpError } from '$lib/admin/infrastructure/transport';
import type { FilesApi } from '$lib/files/api';
import type { NodeSummary } from '$lib/files/domain/schemas';
import { deferred, fileId, filesystemFixture, folderId, rootId } from '$lib/files/fixtures.test-support';
import { InMemoryFilesApi } from '$lib/files/infrastructure/in-memory-api.test-support';
import { FilesState, filesHref } from '$lib/files/state/files-state.svelte';
import { UploadState } from '$lib/files/state/upload-state.svelte';
import { NewFolderState } from '$lib/files/state/new-folder-state.svelte';
import { workspaceNavigation } from '$lib/workspace/navigation';
import FilesContent from './FilesContent.svelte';
import FilesPage from './FilesPage.svelte';
import NewFolderForm from './NewFolderForm.svelte';

const navigation = vi.hoisted(() => ({ callback: undefined as ((event: { to: { url: URL } | null }) => void) | undefined }));
vi.mock('$app/navigation', () => ({
  invalidateAll: vi.fn(),
  goto: vi.fn(),
  afterNavigate: (callback: (event: { to: { url: URL } | null }) => void): void => { navigation.callback = callback; }
}));

function fixture(): { api: FilesApi; state: FilesState; folder: NewFolderState; upload: UploadState } {
  const api: FilesApi = new InMemoryFilesApi(rootId, filesystemFixture);
  const state = new FilesState(api);
  return { api, state, folder: new NewFolderState(api, state), upload: new UploadState(api, state) };
}

function content(state: FilesState, folder: NewFolderState, upload: UploadState): string {
  return render(FilesContent, { props: { state, folder, upload, signIn: vi.fn() } }).body;
}

describe('Files user composition', () => {
  test('Files navigation exists for both regular and administrator workspaces', (): void => {
    for (const allowed of [false, true]) {
      expect(workspaceNavigation(allowed)).toContainEqual({ id: 'files', label: 'Files', href: '/files' });
    }
    expect(workspaceNavigation(false).some((item) => item.href.startsWith('/admin'))).toBe(false);
  });

  test('shell renders unprivileged and loads every URL selection including history navigation independently', async (): Promise<void> => {
    const { api } = fixture();
    const getRoot = vi.spyOn(api.filesystem, 'getRoot');
    const getNode = vi.spyOn(api.filesystem, 'getNode');
    const getChildren = vi.spyOn(api.filesystem, 'listChildren');
    const currentUser = vi.fn(() => deferred<never>().promise);
    const body = render(FilesPage, { props: { createApi: () => api, createCurrentUserApi: () => ({ currentUser }) } }).body;
    expect(body).toContain('aria-label="Workspace navigation"');
    expect(body).toContain('href="/files"');
    expect(body).not.toContain('href="/admin"');
    expect(body).toContain('Loading files');
    expect(getRoot).not.toHaveBeenCalled();
    navigation.callback?.({ to: { url: new URL('https://umbod.test/files') } });
    await vi.waitFor(() => expect(getChildren).toHaveBeenCalledWith(rootId, expect.any(AbortSignal)));
    navigation.callback?.({ to: { url: new URL('https://umbod.test' + filesHref(folderId)) } });
    await vi.waitFor(() => expect(getChildren).toHaveBeenCalledWith(folderId, expect.any(AbortSignal)));
    navigation.callback?.({ to: { url: new URL('https://umbod.test/files') } });
    await vi.waitFor(() => expect(getRoot).toHaveBeenCalledTimes(2));
    await vi.waitFor(() => expect(getChildren).toHaveBeenCalledTimes(3));
    navigation.callback?.({ to: { url: new URL('https://umbod.test' + filesHref(fileId)) } });
    await vi.waitFor(() => expect(getNode).toHaveBeenCalledWith(fileId, expect.any(AbortSignal)));
    expect(getChildren).toHaveBeenCalledTimes(3);
    expect(currentUser).not.toHaveBeenCalled();
  });

  test('root is labelled Files with accessible compact items and authorized upload', async (): Promise<void> => {
    const { state, folder, upload } = fixture();
    await state.load(null);
    await vi.waitFor(() => expect(upload.available).toBe(true));
    const body = content(state, folder, upload);
    expect(body).toContain('Files</h1>');
    expect(body).not.toContain('aria-label="File path"');
    expect(body).toContain('New folder');
    expect(body).toContain('Projects');
    expect(body).toContain('aria-label="Folder"');
    expect(body).toContain('Updated');
    expect(body).toContain('href="' + filesHref(folderId) + '"');
    expect(body).toContain('Upload file');
    expect(body).not.toMatch(/Download|Share|Search|Next page|Create file|New file/);
  });

  test.each([null, folderId])('item rows retain one native navigation link and separate deletion controls in %s', async (selection: string | null): Promise<void> => {
    const { state, folder, upload } = fixture();
    await state.load(selection);
    for (const item of state.children.filter((item) => item.kind === 'file')) {
      await vi.waitFor(() => expect(state.rowDeletion.controllers.get(item.id)?.available).toBe(true));
    }
    const document = new Window().document;
    document.body.innerHTML = content(state, folder, upload);
    const rows = Array.from(document.querySelectorAll('tbody .item-row'));
    expect(rows).toHaveLength(state.children.length);
    for (const [index, row] of rows.entries()) {
      const item = state.children[index];
      const links = row.querySelectorAll('a');
      expect(links).toHaveLength(1);
      expect(links[0].getAttribute('href')).toBe(filesHref(item.id));
      expect(links[0].classList.contains('item-name')).toBe(true);
      expect(row.hasAttribute('tabindex')).toBe(false);
      expect(row.hasAttribute('role')).toBe(false);
      expect(row.hasAttribute('aria-selected')).toBe(false);
      if (item.kind === 'file') {
        const deletion = row.querySelector('button.row-delete');
        expect(deletion?.getAttribute('aria-label')).toBe(`Delete “${item.name}”`);
        expect(deletion?.closest('a')).toBeNull();
      }
    }
  });

  test('deep file details share the authoritative navigation and parent link without duplicate headings', async (): Promise<void> => {
    const { state, folder, upload } = fixture();
    await state.load(fileId);
    const body = content(state, folder, upload);
    expect(body).toContain('aria-label="File details"');
    expect(body).toContain('Notes.txt');
    expect(body).toContain('text/plain');
    expect(body).toContain('Planning');
    expect(body).toContain('aria-label="Parent folder"');
    expect(body).not.toContain(' Up ');
    expect(body).toContain('Projects');
    expect(body).toContain('Notes.txt</h1>');
    expect(body).not.toContain('<h2>Notes.txt');
    expect(body).not.toContain('Open parent folder');
    expect(body).not.toContain('New folder');
    expect(body).not.toMatch(/Upload|Download|Share|Search/);
  });

  test('a stalled listing retains the authorized folder heading and independent navigation without enabling mutations', async (): Promise<void> => {
    const { api, state, folder, upload } = fixture();
    const listing = deferred<NodeSummary[]>();
    vi.spyOn(api.filesystem, 'listChildren').mockReturnValueOnce(listing.promise);
    const uploadEligibility = vi.spyOn(api.filesystem, 'checkUploadEligibility');
    const loading = state.load(folderId);
    await vi.waitFor(() => expect(state.navigation.phase).toBe('ready'));
    const document = new Window().document;
    document.body.innerHTML = content(state, folder, upload);
    expect(document.querySelector('#files-heading')?.textContent).toBe('Projects');
    expect(document.querySelector('.mobile-path a')?.getAttribute('href')).toBe('/files');
    expect(document.querySelector('nav[aria-label="File path"] [aria-current="page"]')?.textContent).toBe('Projects');
    expect(document.body.textContent).toContain('Loading files');
    expect(state.phase).toBe('loading');
    expect(state.creationTarget()).toBeUndefined();
    expect(uploadEligibility).not.toHaveBeenCalled();
    expect(document.querySelector('#upload-file-button, #new-folder-button, .row-delete')).toBeNull();
    listing.resolve([filesystemFixture[2]]);
    await loading;
    expect(state.phase).toBe('ready');
  });

  test.each([
    [new Error('private listing diagnostic'), "Couldn't load files"],
    [new HttpError(403, 'private listing diagnostic', {}), "You don't have access"]
  ])('a failed listing retains the authorized heading and path without granting ready actions', async (error, message): Promise<void> => {
    const { api, state, folder, upload } = fixture();
    vi.spyOn(api.filesystem, 'listChildren').mockRejectedValueOnce(error);
    const uploadEligibility = vi.spyOn(api.filesystem, 'checkUploadEligibility');
    await state.load(folderId);
    await vi.waitFor(() => expect(state.navigation.phase).toBe('ready'));
    const document = new Window().document;
    document.body.innerHTML = content(state, folder, upload);
    expect(document.querySelector('#files-heading')?.textContent).toBe('Projects');
    expect(document.querySelector('.mobile-path a')?.getAttribute('href')).toBe('/files');
    expect(document.querySelector('nav[aria-label="File path"] [aria-current="page"]')?.textContent).toBe('Projects');
    expect(document.body.textContent).toContain(message);
    expect(document.body.textContent).not.toContain('private listing diagnostic');
    expect(document.body.textContent).not.toContain('This folder is empty');
    expect(state.phase).not.toBe('ready');
    expect(state.creationTarget()).toBeUndefined();
    expect(uploadEligibility).not.toHaveBeenCalled();
    expect(document.querySelector('#upload-file-button, #new-folder-button, .row-delete')).toBeNull();
  });

  test('renders empty, loading, denied and failed states distinctly', async (): Promise<void> => {
    const { api, state, folder, upload } = fixture();
    expect(content(state, folder, upload)).toContain('Loading files');
    vi.spyOn(api.filesystem, 'listChildren').mockResolvedValueOnce([]);
    await state.load(null);
    expect(content(state, folder, upload)).toContain('This folder is empty.');
    vi.spyOn(api.filesystem, 'getRoot').mockRejectedValueOnce(new HttpError(403, 'Forbidden', {}));
    await state.load(null);
    expect(content(state, folder, upload)).toContain("You don't have access");
    expect(content(state, folder, upload)).not.toContain('This folder is empty.');
    expect(content(state, folder, upload)).not.toContain('New folder');
    vi.spyOn(api.filesystem, 'getRoot').mockRejectedValueOnce(new Error('private diagnostic'));
    await state.reload();
    expect(content(state, folder, upload)).toContain("Couldn't load files");
    expect(content(state, folder, upload)).not.toContain('private diagnostic');
  });

  test('folder form preserves denied input, disables all submits while pending and exposes uncertainty reload', async (): Promise<void> => {
    const { api, state, folder } = fixture();
    await state.load(null);
    folder.show();
    folder.changeName('Keep me');
    vi.spyOn(api.filesystem, 'createFolder').mockRejectedValueOnce(new HttpError(403, 'Forbidden', {}));
    await folder.submit();
    const rejected = render(NewFolderForm, { props: { state: folder } }).body;
    expect(rejected).toContain('aria-label="New folder"');
    expect(rejected).toContain('for="folder-name"');
    expect(rejected).toContain('value="Keep me"');
    expect(rejected).toContain('role="alert"');
    const pending = deferred<never>();
    vi.spyOn(api.filesystem, 'createFolder').mockImplementationOnce(() => pending.promise);
    const write = folder.submit();
    const busy = render(NewFolderForm, { props: { state: folder } }).body;
    expect(busy).toMatch(/<input[^>]*disabled/);
    expect(busy).toMatch(/<button[^>]*type="submit"[^>]*disabled/);
    pending.reject(new Error('lost reply'));
    await write;
    expect(render(NewFolderForm, { props: { state: folder } }).body).toContain('Reload folder');
  });
});
