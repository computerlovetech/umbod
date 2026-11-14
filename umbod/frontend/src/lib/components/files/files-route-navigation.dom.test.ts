import { afterEach, describe, expect, test, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import { deferred, filesystemFixture, folderId, rootId } from '$lib/files/fixtures.test-support';
import { InMemoryFilesApi } from '$lib/files/infrastructure/in-memory-api.test-support';
import FilesPage from './FilesPage.svelte';

const navigation = vi.hoisted(() => ({ callback: undefined as ((event: { to: { url: URL } | null }) => void) | undefined }));
vi.mock('$app/navigation', () => ({
  goto: vi.fn(),
  invalidateAll: vi.fn(),
  afterNavigate: (callback: (event: { to: { url: URL } | null }) => void): void => { navigation.callback = callback; }
}));

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  navigation.callback = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

function navigate(path: string): void {
  expect(navigation.callback).toBeDefined();
  navigation.callback!({ to: { url: new URL(path, 'https://umbod.test') } });
}

function newFolderButton(): HTMLButtonElement {
  const button = document.querySelector<HTMLButtonElement>('#new-folder-button');
  expect(button).not.toBeNull();
  return button!;
}

describe('Files route incidental navigation', (): void => {
  test('hash, unrelated query and personal-root UUID alias preserve creation drafts without reloading', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    const browse = vi.spyOn(api.filesystem, 'browse');
    const discovery = vi.spyOn(api.filesystem, 'listNamespaces');
    const target = document.createElement('div');
    document.body.append(target);
    component = mount(FilesPage, { target, props: { createApi: () => api, createWorkspaceApi: () => ({ profile: { get: () => deferred<never>().promise } }) } });
    await tick();
    navigate('/files');
    await vi.waitFor(() => expect(document.querySelector('#new-folder-button')).not.toBeNull());
    await tick();
    newFolderButton().click();
    await tick();
    const input = document.querySelector<HTMLInputElement>('#folder-name');
    expect(input).not.toBeNull();
    input!.value = 'Keep my draft';
    input!.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();
    for (const path of ['/files#details', '/files?unrelated=value', '/files?node=' + rootId + '#details', '/files']) {
      navigate(path);
      await tick();
      expect(document.querySelector('#folder-name')).toBe(input);
      expect(input!.value).toBe('Keep my draft');
      expect(browse).toHaveBeenCalledTimes(1);
      expect(discovery).toHaveBeenCalledTimes(1);
    }
    navigate('/files?node=' + folderId);
    await vi.waitFor(() => expect(browse).toHaveBeenCalledTimes(2));
    await tick();
    expect(document.querySelector('#folder-name')).toBeNull();
    expect(document.querySelector('#files-heading')?.textContent).toBe('Files');
  });
});
