import { render } from 'svelte/server';
import { describe, expect, test, vi } from 'vitest';
import { HttpError } from '$lib/admin/infrastructure/transport';
import type { FilesApi } from '$lib/files/api';
import { deferred, fileId, filesystemFixture, folderId, rootId } from '$lib/files/fixtures.test-support';
import { InMemoryFilesApi } from '$lib/files/infrastructure/in-memory-api';
import { FilesState, filesHref } from '$lib/files/state/files-state.svelte';
import { UploadState } from '$lib/files/state/upload-state.svelte';
import { NewFolderState } from '$lib/files/state/new-folder-state.svelte';
import { workspaceNavigation } from '$lib/workspace/navigation';
import FilesContent from './FilesContent.svelte';
import FilesPage from './FilesPage.svelte';
import NewFolderForm from './NewFolderForm.svelte';

const navigation = vi.hoisted(() => ({ callback: undefined as ((event: { to: { url: URL } | null }) => void) | undefined }));
vi.mock('$app/navigation', () => ({
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
    expect(body).toContain('aria-label="Visited folders"');
    expect(body).toContain('New folder');
    expect(body).toContain('Projects');
    expect(body).toContain('aria-label="Folder"');
    expect(body).toContain('Updated');
    expect(body).toContain('href="' + filesHref(folderId) + '"');
    expect(body).toContain('Upload file');
    expect(body).not.toMatch(/Download|Share|Search|Next page|Create file|New file/);
  });

  test('deep file details show metadata and an explicit parent link, with no ancestor names or writes', async (): Promise<void> => {
    const { state, folder, upload } = fixture();
    await state.load(fileId);
    const body = content(state, folder, upload);
    expect(body).toContain('aria-label="File details"');
    expect(body).toContain('Notes.txt');
    expect(body).toContain('text/plain');
    expect(body).toContain('Planning');
    expect(body).toContain('Open parent folder');
    expect(body).not.toContain('Projects');
    expect(body).not.toContain('New folder');
    expect(body).not.toMatch(/Upload|Download|Share|Search/);
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
