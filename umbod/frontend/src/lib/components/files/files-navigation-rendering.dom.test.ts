import { afterEach, describe, expect, test, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import { deferred, fileId, filesystemFixture, folderId, rootId } from '#lib/files/fixtures.test-support.js';
import type { BrowseResult } from '#lib/files/domain/schemas.js';
import { InMemoryFilesApi } from '#lib/files/infrastructure/in-memory-api.test-support.js';
import { FilesState } from '#lib/files/state/files-state.svelte.js';
import { NewFolderState } from '#lib/files/state/new-folder-state.svelte.js';
import { UploadState } from '#lib/files/state/upload-state.svelte.js';
import FilesContent from './FilesContent.svelte';

let component: ReturnType<typeof mount> | undefined;
let files: FilesState | undefined;
let folder: NewFolderState | undefined;
let upload: UploadState | undefined;

afterEach(async (): Promise<void> => {
  upload?.dispose();
  folder?.dispose();
  files?.dispose();
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

async function setup(namespaces: boolean = false): Promise<{ api: InMemoryFilesApi; state: FilesState }> {
  const api = new InMemoryFilesApi(rootId, filesystemFixture);
  if (namespaces) {
    const inventory = await api.filesystem.listNamespaces();
    vi.spyOn(api.filesystem, 'listNamespaces').mockResolvedValue([...inventory, { ...inventory[0], id: folderId, root_node_id: folderId, kind: 'shared', name: 'Team files' }]);
  }
  const state = new FilesState(api);
  files = state;
  folder = new NewFolderState(api, state);
  upload = new UploadState(api, state);
  const target = document.createElement('div');
  document.body.append(target);
  component = mount(FilesContent, { target, props: { state, folder, upload, signIn: vi.fn() } });
  await state.load(null);
  await tick();
  return { api, state };
}

function button(selector: string): HTMLButtonElement {
  const element = document.querySelector<HTMLButtonElement>(selector);
  expect(element).not.toBeNull();
  return element!;
}

function currentMenu(): HTMLButtonElement {
  return button('[aria-label="Location actions"] button[aria-haspopup="menu"]');
}

function openDetails(): void {
  const item = Array.from(document.querySelectorAll<HTMLButtonElement>('[role="menuitem"]')).find((candidate) => candidate.textContent?.trim() === 'View details');
  expect(item).toBeDefined();
  item!.click();
}

describe('Files retained navigation rendering', (): void => {
  test.each([false, true])('directory navigation preserves header controls and SVGs with namespace switching %s', async (namespaces): Promise<void> => {
    const { api, state } = await setup(namespaces);
    const controls = [button('#upload-file-button'), button('#new-folder-button'), currentMenu()];
    const icons = controls.map((control) => control.querySelector('svg'));
    const rootRow = document.querySelector('tbody tr');
    const snapshot = await api.filesystem.browse(folderId);
    const pending = deferred<BrowseResult>();
    const browse = vi.spyOn(api.filesystem, 'browse').mockReturnValueOnce(pending.promise);
    currentMenu().click();
    await tick();
    expect(document.querySelector('[role="menu"]')).not.toBeNull();
    const loading = state.load(folderId);
    await vi.waitFor(() => expect(browse).toHaveBeenCalledTimes(1));
    await tick();
    expect(document.querySelector('[role="menu"]')).toBeNull();
    expect(document.querySelector('tbody tr')).toBe(rootRow);
    expect(document.querySelector('[inert][aria-busy="true"]')?.contains(rootRow)).toBe(true);
    expect(rootRow?.closest('.delayed-loading-overlay')).not.toBeNull();
    const loadingStatus = Array.from(document.querySelectorAll('p[role="status"]')).find((status) => status.textContent === 'Loading files…');
    expect(loadingStatus?.classList.contains('visually-hidden')).toBe(true);
    expect(document.querySelector('aside')?.closest('[inert]')).toBeNull();
    expect(document.querySelector('nav[aria-label="File locations"] [aria-current="page"]')?.getAttribute('href')).toContain(rootId);
    controls.forEach((control, index) => {
      expect(control.isConnected).toBe(true);
      expect(control.disabled).toBe(true);
      expect(control.querySelector('svg')).toBe(icons[index]);
    });
    currentMenu().click();
    await tick();
    expect(document.querySelector('[role="menu"]')).toBeNull();
    pending.resolve(snapshot);
    await loading;
    await tick();
    [button('#upload-file-button'), button('#new-folder-button'), currentMenu()].forEach((control, index) => expect(control).toBe(controls[index]));
    controls.forEach((control, index) => {
      expect(control.disabled).toBe(false);
      expect(control.querySelector('svg')).toBe(icons[index]);
    });
    expect(document.querySelector('[inert]')).toBeNull();
    expect(document.querySelector('#files-heading')?.textContent).toBe('Files');
    expect(currentMenu().getAttribute('aria-label')).toBe(namespaces ? 'Actions for “Team files”' : 'Actions for “Projects”');
    expect(document.querySelector('[role="menu"]')).toBeNull();
  });

  test.each([false, true])('root and folder navigation show namespace names beside the title with namespace switching %s', async (namespaces): Promise<void> => {
    const { state } = await setup(namespaces);
    const pathSlot = document.querySelector('.location-navigation');
    expect(pathSlot).not.toBeNull();
    expect(document.querySelector('header .node-identity')?.contains(pathSlot)).toBe(true);
    expect(document.querySelector('[aria-label="Files content"]')?.contains(pathSlot)).toBe(false);
    expect(pathSlot?.querySelector('[aria-current="page"]')?.textContent).toBe('My files');
    expect(document.querySelector('thead')).not.toBeNull();
    await state.load(folderId);
    await tick();
    expect(document.querySelector('.location-navigation')).toBe(pathSlot);
    expect(pathSlot?.querySelector('[aria-current="page"]')?.textContent).toBe(namespaces ? 'Team files' : 'Projects');
    expect(document.querySelector('thead')).not.toBeNull();
    await state.load(rootId);
    await tick();
    expect(document.querySelector('.location-navigation')).toBe(pathSlot);
    expect(pathSlot?.querySelector('[aria-current="page"]')?.textContent).toBe('My files');
    expect(document.querySelector('thead')).not.toBeNull();
  });

  test('folder and file navigation retain the path bar and action container while creation controls disappear', async (): Promise<void> => {
    const { state } = await setup();
    await state.load(folderId);
    await tick();
    const path = document.querySelector('.location-navigation');
    const actions = document.querySelector('[aria-label="Location actions"]');
    const menu = currentMenu();
    expect(path).not.toBeNull();
    expect(actions).not.toBeNull();
    expect(button('#upload-file-button').isConnected).toBe(true);
    expect(button('#new-folder-button').isConnected).toBe(true);

    await state.load(fileId);
    await tick();
    expect(document.querySelector('.location-navigation')).toBe(path);
    expect(document.querySelector('[aria-label="Location actions"]')).toBe(actions);
    expect(currentMenu()).toBe(menu);
    expect(actions!.querySelector('#upload-file-button, #new-folder-button')).toBeNull();

    await state.load(folderId);
    await tick();
    expect(document.querySelector('.location-navigation')).toBe(path);
    expect(document.querySelector('[aria-label="Location actions"]')).toBe(actions);
    expect(currentMenu()).toBe(menu);
    expect(button('#upload-file-button').disabled).toBe(false);
    expect(button('#new-folder-button').disabled).toBe(false);
  });

  test('same-folder refresh keeps rows, icons and menu triggers while closing details and popups permanently', async (): Promise<void> => {
    const { api, state } = await setup();
    await state.load(folderId);
    await tick();
    const row = document.querySelector('tbody tr');
    const icon = row?.querySelector('a svg');
    const trigger = button('tbody button[aria-haspopup="menu"]');
    trigger.click();
    await tick();
    openDetails();
    await tick();
    expect(document.querySelector('dialog')).not.toBeNull();
    const snapshot = await api.filesystem.browse(folderId);
    const pending = deferred<BrowseResult>();
    vi.spyOn(api.filesystem, 'browse').mockReturnValueOnce(pending.promise);
    const loading = state.reload();
    await tick();
    expect(document.querySelector('dialog')).toBeNull();
    expect(trigger.disabled).toBe(true);
    pending.resolve(snapshot);
    await loading;
    await tick();
    expect(document.querySelector('tbody tr')).toBe(row);
    expect(row?.querySelector('a svg')).toBe(icon);
    expect(button('tbody button[aria-haspopup="menu"]')).toBe(trigger);
    expect(document.querySelector('dialog, [role="menu"]')).toBeNull();
    trigger.click();
    await tick();
    expect(document.querySelector('[role="menu"]')).not.toBeNull();
    await state.reload();
    await tick();
    expect(document.querySelector('[role="menu"]')).toBeNull();
    expect(button('tbody button[aria-haspopup="menu"]')).toBe(trigger);
    expect(row?.querySelector('a svg')).toBe(icon);
  });

  test('updating one row preserves the unaffected row and both action triggers', async (): Promise<void> => {
    const { api, state } = await setup();
    const created = await api.filesystem.createFolder(rootId, { name: 'Unchanged', metadata: { content_type: {}, attributes: {} } });
    await state.reload();
    await tick();
    const unchanged = document.querySelector(`a[href="/files?node=${created.id}"]`)?.closest('tr');
    const changed = document.querySelector(`tbody a[href="/files?node=${folderId}"]`)?.closest('tr');
    const icon = unchanged?.querySelector('svg');
    const unchangedTrigger = unchanged?.querySelector('button');
    const changedTrigger = changed?.querySelector('button');
    expect(unchanged).not.toBeNull();
    expect(changed).not.toBeNull();
    changedTrigger!.click();
    await tick();
    const rename = Array.from(document.querySelectorAll<HTMLButtonElement>('[role="menuitem"]')).find((item) => item.textContent?.trim() === 'Rename');
    expect(rename).toBeDefined();
    rename!.click();
    await tick();
    const input = document.querySelector<HTMLInputElement>('#node-rename');
    expect(input).not.toBeNull();
    input!.value = 'Updated folder';
    input!.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();
    const submit = document.querySelector<HTMLButtonElement>('dialog button[type="submit"]');
    expect(submit).not.toBeNull();
    submit!.click();
    await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
    expect(document.querySelector(`tbody a[href="/files?node=${folderId}"]`)?.textContent).toContain('Updated folder');
    expect(document.querySelector(`tbody a[href="/files?node=${created.id}"]`)?.closest('tr')).toBe(unchanged);
    expect(unchanged?.querySelector('svg')).toBe(icon);
    expect(unchanged?.querySelector('button')).toBe(unchangedTrigger);
    expect(changed?.querySelector('button')).toBe(changedTrigger);
    expect(state.children.some((node) => node.id === fileId)).toBe(false);
  });
});
