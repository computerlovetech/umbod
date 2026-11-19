import { afterEach, describe, expect, test, vi } from 'vitest';
import { mountWorkspace } from '#lib/components/workspace/mount-workspace.test-support.js';
import { tick, unmount } from 'svelte';
import { deferred, fileId, filesystemFixture, folderId, rootId } from '#lib/files/fixtures.test-support.js';
import { InMemoryFilesApi } from '#lib/files/infrastructure/in-memory-api.test-support.js';
import FilesPage from './FilesPage.svelte';
import { filesHref, sharedWithMeHref } from '#lib/files/state/files-state.svelte.js';
import type { NodeSummary } from '#lib/files/domain/schemas.js';
import { InMemoryPreviewConfiguration } from '#lib/files/preview/in-memory-configuration.test-support.js';
import { InMemoryFileContent } from '#lib/files/preview/in-memory-content.test-support.js';

const navigation = vi.hoisted(() => ({ callback: undefined as ((event: { to: { url: URL } | null; shallow?: boolean }) => void) | undefined }));
vi.mock('$app/navigation', () => ({
  goto: vi.fn(),
  refreshAll: vi.fn(),
  afterNavigate: (callback: (event: { to: { url: URL } | null; shallow?: boolean }) => void): void => { navigation.callback = callback; }
}));

let component: ReturnType<typeof mountWorkspace> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  navigation.callback = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

function navigate(path: string, shallow = false): void {
  expect(navigation.callback).toBeDefined();
  navigation.callback!({ to: { url: new URL(path, 'https://umbod.test') }, shallow });
}

function newFolderButton(): HTMLButtonElement {
  const button = document.querySelector<HTMLButtonElement>('#new-folder-button');
  expect(button).not.toBeNull();
  return button!;
}

function href(selector: string): string {
  const anchor = document.querySelector<HTMLAnchorElement>(selector);
  expect(anchor).not.toBeNull();
  return anchor!.getAttribute('href')!;
}

test('Shared with me links open the normal folder and preview while retaining an explicit return URL', async (): Promise<void> => {
  const privateNamespace = 'Private namespace name';
  const nodes = filesystemFixture.map((node): NodeSummary => node.id === fileId ? {
    ...node, visible_to: { type: 'namespace', namespace_id: folderId, kind: 'shared', name: privateNamespace }
  } : node);
  const api = new InMemoryFilesApi(rootId, nodes);
  const pending = deferred<NodeSummary[]>();
  const listing = vi.spyOn(api.filesystem, 'listSharedWithMe')
    .mockReturnValueOnce(pending.promise)
    .mockResolvedValueOnce([filesystemFixture[1], filesystemFixture[2]])
    .mockResolvedValue([]);
  const source = new InMemoryFileContent(async (): Promise<string> => 'Shared document body');
  const target = document.createElement('div');
  document.body.append(target);
  component = mountWorkspace(FilesPage, { target, props: {
    createApi: () => api,
    configuration: new InMemoryPreviewConfiguration(1024),
    createContentSource: () => source,
    createWorkspaceApi: () => ({ profile: { get: () => deferred<never>().promise } })
  } }, '/files');
  await tick();
  navigate('/files');
  await vi.waitFor(() => expect(document.querySelector('#new-folder-button')).not.toBeNull());
  navigate(href('nav[aria-label="File locations"] a[href="/files?shared-with-me"]'));
  await tick();
  expect(document.body.textContent).toContain('Loading Shared with me…');
  expect(document.body.textContent).not.toContain('Nothing has been shared');
  pending.reject(new Error('offline'));
  await vi.waitFor(() => expect(document.body.textContent).toContain("Couldn't load Shared with me."));
  const retry = Array.from(target.querySelectorAll('button')).find((button) => button.textContent?.trim() === 'Retry');
  expect(retry).toBeDefined();
  retry!.click();
  const table = 'table[aria-label="Files and folders shared with me"]';
  await vi.waitFor(() => expect(target.querySelector(table)).not.toBeNull());
  expect(target.querySelector('[aria-label="Location actions"], .row-actions, tr[draggable="true"]')).toBeNull();
  expect(target.querySelectorAll(`${table} tbody a`)).toHaveLength(2);
  expect(href(`${table} a[title="Notes.txt"]`)).toBe(filesHref(fileId, fileId));

  navigate(href(`${table} a[title="Projects"]`));
  await vi.waitFor(() => expect(target.querySelector('#new-folder-button')).not.toBeNull());
  const back = 'a.shared-back';
  expect(href(back)).toBe(sharedWithMeHref);
  const child = href('table a[title="Notes.txt"]');
  expect(child).toBe(filesHref(fileId, folderId));
  navigate(child);
  await vi.waitFor(() => expect(target.textContent).toContain('Shared document body'));
  expect(target.querySelector('nav[aria-label="File path"]')?.textContent).not.toContain('My files');
  expect(href('nav[aria-label="File path"] a[title="Projects"]')).toBe(filesHref(folderId, folderId));
  expect(href(back)).toBe(sharedWithMeHref);
  expect(listing).toHaveBeenCalledTimes(2);
  const detailsAction = (label: string): HTMLButtonElement => {
    const button = Array.from(target.querySelectorAll('button')).find((button) => (button.getAttribute('aria-label') ?? button.textContent?.trim()) === label);
    expect(button).toBeDefined();
    return button!;
  };
  detailsAction('Actions for “Notes.txt”').click();
  await tick();
  detailsAction('View details').click();
  await vi.waitFor(() => expect(document.querySelector('[role="dialog"]')?.textContent).toContain('Restricted'));
  expect(document.querySelector('[role="dialog"]')?.textContent).not.toContain(privateNamespace);

  navigate(href(back));
  await vi.waitFor(() => expect(target.textContent).toContain('Nothing has been shared with you yet.'));
  expect(target.querySelector('nav[aria-label="File locations"] a[aria-current="page"]')?.textContent?.trim()).toBe('Shared with me');
  navigate(filesHref(fileId));
  await vi.waitFor(() => expect(target.textContent).toContain('Shared document body'));
  expect(target.querySelector(back)).toBeNull();
  expect(target.querySelector('nav[aria-label="File path"]')?.textContent).toContain('My files');
});

test('saving sharing shows one confirmation in the workspace Notifications region', async (): Promise<void> => {
  const api = new InMemoryFilesApi(rootId, filesystemFixture);
  api.sharing.configure({ node_id: fileId, revision: 'initial', grants: [], blocked_recipients: [] }, []);
  const target = document.createElement('div');
  document.body.append(target);
  component = mountWorkspace(FilesPage, { target, props: {
    createApi: () => api,
    createWorkspaceApi: () => ({ profile: { get: () => deferred<never>().promise } })
  } }, '/files');
  await tick();
  navigate(filesHref(folderId));
  const click = async (selector: string): Promise<void> => {
    const control = await vi.waitFor(() => {
      const button = target.querySelector<HTMLButtonElement>(selector);
      expect(button?.disabled).toBe(false);
      return button!;
    });
    control.click();
  };
  await click('button[aria-label="Actions for “Notes.txt”"]');
  await click('button[aria-label="Share “Notes.txt”"]');
  await click('dialog button[type="submit"]');
  const message = 'Sharing updated for “Notes.txt”.';
  await vi.waitFor(() => expect(target.querySelector('[aria-label="Notifications"]')?.textContent).toContain(message));
  expect(target.querySelector('[aria-label="Files content"]')?.textContent).not.toContain(message);
  expect(target.querySelector('dialog')).toBeNull();
});

describe('Files route incidental navigation', (): void => {
  test('hash, unrelated query and personal-root UUID alias preserve creation drafts without reloading', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    const browse = vi.spyOn(api.filesystem, 'browse');
    const discovery = vi.spyOn(api.filesystem, 'listNamespaces');
    const target = document.createElement('div');
    document.body.append(target);
    component = mountWorkspace(FilesPage, { target, props: { createApi: () => api, createWorkspaceApi: () => ({ profile: { get: () => deferred<never>().promise } }) } }, '/files');
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
    navigate('/files?node=' + folderId, true);
    await tick();
    expect(document.querySelector('#folder-name')).toBe(input);
    expect(input!.value).toBe('Keep my draft');
    expect(browse).toHaveBeenCalledTimes(1);
    navigate('/files?node=' + folderId);
    await vi.waitFor(() => expect(browse).toHaveBeenCalledTimes(2));
    await tick();
    expect(document.querySelector('#folder-name')).toBeNull();
    expect(document.querySelector('#files-heading')?.textContent).toBe('Files');
  });
});
