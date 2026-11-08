import { afterEach, describe, expect, test, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import { HttpError } from '$lib/admin/infrastructure/transport';
import type { NodeSummary } from '$lib/files/domain/schemas';
import { deferred, fileId, filesystemFixture, filesystemNode, folderId, rootId } from '$lib/files/fixtures.test-support';
import { InMemoryFilesApi } from '$lib/files/infrastructure/in-memory-api.test-support';
import { FilesState } from '$lib/files/state/files-state.svelte';
import { NewFolderState } from '$lib/files/state/new-folder-state.svelte';
import { UploadState } from '$lib/files/state/upload-state.svelte';
import FilesContent from './FilesContent.svelte';
import NodeUpdateDialog from './NodeUpdateDialog.svelte';
import { NodeUpdateState } from '$lib/files/state/node-update-state.svelte';

let component: ReturnType<typeof mount> | undefined;
let files: FilesState | undefined;

afterEach(async (): Promise<void> => {
  files?.dispose();
  if (component) await unmount(component);
  component = undefined;
  files = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

function button(label: string, scope: ParentNode = document): HTMLButtonElement {
  const found = Array.from(scope.querySelectorAll('button')).find((candidate) => candidate.textContent?.trim() === label);
  expect(found, label).toBeDefined();
  return found!;
}

function namedButton(label: string): HTMLButtonElement {
  const found = Array.from(document.querySelectorAll('button')).find((candidate) => candidate.getAttribute('aria-label') === label);
  expect(found, label).toBeDefined();
  return found!;
}

async function waitForFolders(): Promise<void> {
  await tick();
  await vi.waitFor(() => expect(document.querySelector('[aria-label="Destination folders"]')?.getAttribute('aria-busy')).toBe('false'));
  await tick();
}

async function openAction(label: string): Promise<void> {
  document.querySelector<HTMLButtonElement>('.heading-identity button[aria-haspopup="menu"]')!.click();
  await tick();
  button(label).click();
  await tick();
}

async function setup(id: string | null, writable = true, api = new InMemoryFilesApi(rootId, filesystemFixture, undefined, undefined, undefined, () => writable)): Promise<InMemoryFilesApi> {
  const state = new FilesState(api);
  files = state;
  const target = document.createElement('div');
  document.body.append(target);
  component = mount(FilesContent, { target, props: { state, folder: new NewFolderState(api, state), upload: new UploadState(api, state), signIn: vi.fn() } });
  await state.load(id);
  await vi.waitFor(() => expect(state.phase).toBe('ready'));
  await tick();
  return api;
}

describe('selected node update controls', (): void => {
  test('renders only the home-relative destination path and Files label after the home is renamed', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    const state = new NodeUpdateState(api.filesystem, (): void => {}, async (): Promise<void> => {}, () => folderId);
    try {
      await api.filesystem.updateNode(folderId, 1, { name: 'Renamed home' });
      await state.select(await api.filesystem.getNode(fileId), { rename: true, move: true });
      state.showMove();
      await vi.waitFor(() => expect(state.destinations.loading).toBe(false));
      const target = document.createElement('div');
      document.body.append(target);
      component = mount(NodeUpdateDialog, { target, props: { state } });
      await tick();
      const picker = document.querySelector('[aria-label="Destination folders"]')!;
      expect(picker.querySelectorAll('button')).toHaveLength(1);
      expect(namedButton('Select Files').disabled).toBe(true);
      expect(picker.textContent).toContain('Current');
      expect(picker.textContent).not.toContain('Shared files');
      expect(document.querySelector('dialog')?.textContent).not.toContain('Renamed home');
    } finally {
      state.dispose();
    }
  });

  test.each([[folderId, fileId, 'Renamed.txt'], [rootId, folderId, 'Renamed folder']])('renames the row child of %s without changing the parent', async (parentId, childId, name): Promise<void> => {
    const api = await setup(parentId);
    await vi.waitFor(() => expect(files?.rowEditing.controllers.get(childId)?.update.canRename).toBe(true));
    await tick();
    const heading = document.querySelector('h1');
    const trigger = document.querySelector<HTMLButtonElement>('tbody button[aria-haspopup="menu"]')!;
    expect(trigger.closest('td')?.classList.contains('row-actions')).toBe(true);
    expect(document.querySelector('[aria-label="Description"] button')).toBeNull();
    trigger.click();
    await tick();
    button('Rename').click();
    await tick();
    expect(document.querySelector('[role="menu"]')).toBeNull();
    const input = document.querySelector<HTMLInputElement>('#node-rename')!;
    input.value = name;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();
    button('Rename', document.querySelector('dialog')!).click();
    await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
    expect((await api.filesystem.getNode(childId)).name).toBe(name);
    expect(files?.node?.id).toBe(parentId);
    expect(document.querySelector('h1')).toBe(heading);
    expect(document.querySelector('tbody')?.textContent).toContain(name);
  });

  test('moves a row to another folder and restores focus to the retained heading', async (): Promise<void> => {
    const api = await setup(folderId);
    await vi.waitFor(() => expect(files?.rowEditing.controllers.get(fileId)?.update.canMove).toBe(true));
    await tick();
    document.querySelector<HTMLButtonElement>('tbody button[aria-haspopup="menu"]')!.click();
    await tick();
    button('Move').click();
    await waitForFolders();
    namedButton('Select Files').click();
    await vi.waitFor(() => expect(files?.rowEditing.controllers.get(fileId)?.update.canSubmit).toBe(true));
    await tick();
    button('Move to “Files”').click();
    await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
    expect((await api.filesystem.getNode(fileId)).parent_id).toBe(rootId);
    expect(document.querySelector('tbody')).toBeNull();
    expect(document.activeElement).toBe(document.querySelector('h1'));
  });

  test('offers retry when the initial destination path cannot load', async (): Promise<void> => {
    const api = await setup(fileId);
    await vi.waitFor(() => expect(files?.update.canMove).toBe(true));
    await tick();
    vi.spyOn(api.filesystem, 'getBreadcrumbs').mockRejectedValueOnce(new Error('Offline'));
    await openAction('Move');
    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toContain('Could not load folders.'));
    expect(button('Move', document.querySelector('dialog')!).disabled).toBe(true);
    button('Retry folders').click();
    await waitForFolders();
    expect(document.querySelector('[role="alert"]')).toBeNull();
    namedButton('Select Files').click();
    await vi.waitFor(() => expect(button('Move to “Files”').disabled).toBe(false));
  });

  test('retries a failed folder list in its branch without losing the current path', async (): Promise<void> => {
    const api = await setup(fileId);
    await vi.waitFor(() => expect(files?.update.canMove).toBe(true));
    const listChildren = api.filesystem.listChildren;
    vi.spyOn(api.filesystem, 'listChildren').mockImplementation(async (id, signal): Promise<NodeSummary[]> => {
      if (id === rootId) throw new Error('Offline');
      return listChildren(id, signal);
    });
    await openAction('Move');
    await waitForFolders();
    expect(document.querySelector('[role="alert"]')?.textContent).toBe('Could not load folders.');
    expect(namedButton('Collapse Files').getAttribute('aria-expanded')).toBe('true');
    expect(button('Move', document.querySelector('dialog')!).disabled).toBe(true);
    expect(document.querySelector('dialog')?.textContent).not.toContain('Retry folders');
    vi.mocked(api.filesystem.listChildren).mockImplementation(listChildren);
    namedButton('Retry Files').click();
    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')).toBeNull());
    expect(namedButton('Select Projects').disabled).toBe(true);
    expect(namedButton('Select Projects').textContent).toContain('Current');
    expect(document.querySelector('button[aria-label="Expand Projects"]')).toBeNull();
    expect(document.querySelector('button[aria-label="Collapse Projects"]')).toBeNull();
    namedButton('Select Files').click();
    await vi.waitFor(() => expect(button('Move to “Files”').disabled).toBe(false));
  });

  test.each([true, false])('expands a writable=%s folder independently of selection and selects its writable descendant', async (writable): Promise<void> => {
    const archiveId = '00000000-0000-4000-8000-000000000004';
    const reportsId = '00000000-0000-4000-8000-000000000005';
    const api = new InMemoryFilesApi(rootId, [
      ...filesystemFixture,
      filesystemNode({ id: archiveId, parent_id: rootId, name: 'Archive' }),
      filesystemNode({ id: reportsId, parent_id: archiveId, name: 'Reports' })
    ], undefined, undefined, undefined, (node): boolean => node.id !== archiveId || writable);
    await setup(fileId, true, api);
    await vi.waitFor(() => expect(files?.update.canMove).toBe(true));
    await openAction('Move');
    await waitForFolders();
    expect(namedButton('Select Archive').disabled).toBe(!writable);
    if (!writable) expect(namedButton('Select Archive').querySelector('[aria-label="Read only"]')).not.toBeNull();
    expect(namedButton('Expand Archive').disabled).toBe(false);
    namedButton('Expand Archive').click();
    await vi.waitFor(() => expect(document.querySelector('button[aria-label="Select Reports"]')).not.toBeNull());
    expect(namedButton('Collapse Archive').getAttribute('aria-expanded')).toBe('true');
    expect(document.querySelector('[aria-pressed="true"]')).toBeNull();
    expect(button('Move', document.querySelector('dialog')!).disabled).toBe(true);
    if (writable) {
      namedButton('Select Archive').click();
      await vi.waitFor(() => expect(button('Move to “Archive”').disabled).toBe(false));
      expect(namedButton('Select Archive').getAttribute('aria-pressed')).toBe('true');
      expect(namedButton('Select Archive').closest('.folder-row')?.classList.contains('selected')).toBe(true);
      expect(namedButton('Collapse Archive').getAttribute('aria-expanded')).toBe('true');
    }
    namedButton('Select Reports').click();
    await vi.waitFor(() => expect(button('Move to “Reports”').disabled).toBe(false));
    expect(namedButton('Select Reports').getAttribute('aria-pressed')).toBe('true');
    expect(namedButton('Select Reports').closest('.folder-row')?.classList.contains('selected')).toBe(true);
    expect(namedButton('Select Archive').getAttribute('aria-pressed')).toBe('false');
    namedButton('Collapse Archive').click();
    await tick();
    expect(document.querySelector('button[aria-label="Select Reports"]')).toBeNull();
    expect(namedButton('Expand Archive').getAttribute('aria-expanded')).toBe('false');
    expect(document.querySelector('[aria-pressed="true"]')).toBeNull();
    expect(button('Move', document.querySelector('dialog')!).disabled).toBe(true);
  });

  test.each([true, false])('retains keyboard position when a writable=%s folder has no subfolders', async (writable): Promise<void> => {
    const archiveId = '00000000-0000-4000-8000-000000000004';
    const api = new InMemoryFilesApi(rootId, [
      ...filesystemFixture,
      filesystemNode({ id: archiveId, parent_id: rootId, name: 'Archive' })
    ], undefined, undefined, undefined, (node): boolean => node.id !== archiveId || writable);
    await setup(fileId, true, api);
    await vi.waitFor(() => expect(files?.update.canMove).toBe(true));
    await openAction('Move');
    await waitForFolders();
    const children = deferred<NodeSummary[]>();
    vi.spyOn(api.filesystem, 'listChildren').mockReturnValueOnce(children.promise);
    const disclosure = namedButton('Expand Archive');
    disclosure.focus();
    disclosure.click();
    await tick();
    expect(document.activeElement).toBe(disclosure);
    children.resolve([]);
    await vi.waitFor(() => expect(document.querySelector('button[aria-label="Collapse Archive"]')).toBeNull());
    expect(document.activeElement).toBe(disclosure);
    expect(disclosure.getAttribute('aria-label')).toBe('No subfolders in Archive');
    expect(disclosure.getAttribute('aria-disabled')).toBe('true');
    expect(namedButton('Select Archive').disabled).toBe(!writable);
    expect(button('Move', document.querySelector('dialog')!).disabled).toBe(true);
    button('Cancel').focus();
    await tick();
    expect(document.querySelector('button[aria-label="No subfolders in Archive"]')).toBeNull();
    expect(document.activeElement).toBe(button('Cancel'));
  });

  test('uses Shared files when no personal root is configured', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    const state = new NodeUpdateState(api.filesystem, (): void => {}, async (): Promise<void> => {});
    try {
      await state.select(await api.filesystem.getNode(fileId), { rename: true, move: true });
      state.showMove();
      const target = document.createElement('div');
      document.body.append(target);
      component = mount(NodeUpdateDialog, { target, props: { state } });
      await waitForFolders();
      expect(namedButton('Collapse Shared files').getAttribute('aria-expanded')).toBe('true');
      expect(namedButton('Select Shared files').disabled).toBe(false);
      expect(namedButton('Select Projects').disabled).toBe(true);
      namedButton('Select Shared files').click();
      await vi.waitFor(() => expect(button('Move to “Shared files”').disabled).toBe(false));
    } finally {
      state.dispose();
    }
  });

  test.each([null, fileId])('hides root or unauthorized actions for %s', async (id): Promise<void> => {
    await setup(id, id === null);
    await tick();
    const labels = Array.from(document.querySelectorAll('button')).map((candidate) => candidate.textContent?.trim());
    expect(labels).not.toContain('Rename');
    expect(labels).not.toContain('Move');
  });

  test('opens prefilled rename, preserves collision draft and reconciles heading on submit', async (): Promise<void> => {
    const api = await setup(fileId);
    await vi.waitFor(() => expect(files?.update.canRename).toBe(true));
    await tick();
    await openAction('Rename');
    const input = document.querySelector<HTMLInputElement>('#node-rename')!;
    expect(input.value).toBe('Notes.txt');
    input.value = 'Renamed.txt';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();
    vi.spyOn(api.filesystem, 'updateNode').mockRejectedValueOnce(new HttpError(409, 'Collision', {}));
    document.querySelector('form[aria-label="Rename item"]')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await vi.waitFor(() => expect(files?.update.error).toContain('conflicts'));
    expect(input.value).toBe('Renamed.txt');
    button('Rename', document.querySelector('dialog')!).click();
    await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
    expect(document.querySelector('h1')?.textContent).toBe('Renamed.txt');
    expect(files?.node?.id).toBe(fileId);
  });

  test('blocks pending submissions and requires explicit reload after an unknown mutation outcome', async (): Promise<void> => {
    const api = await setup(fileId);
    await vi.waitFor(() => expect(files?.update.canRename).toBe(true));
    await tick();
    await openAction('Rename');
    const input = document.querySelector<HTMLInputElement>('#node-rename')!;
    input.value = 'Pending.txt';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();
    const response = deferred<NodeSummary>();
    const update = vi.spyOn(api.filesystem, 'updateNode').mockReturnValueOnce(response.promise);
    const form = document.querySelector('form[aria-label="Rename item"]')!;
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await tick();
    expect(input.disabled).toBe(true);
    expect(button('Cancel').disabled).toBe(true);
    expect(update).toHaveBeenCalledTimes(1);
    response.reject(new Error('Connection lost'));
    await vi.waitFor(() => expect(files?.update.needsReload).toBe(true));
    await tick();
    expect(input.value).toBe('Pending.txt');
    const reload = vi.spyOn(api.filesystem, 'getNode');
    button('Reload item').click();
    await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
    expect(reload).toHaveBeenCalled();
    expect(files?.update.needsReload).toBe(false);
  });

  test('uses named folder navigation and cancellation without requiring IDs', async (): Promise<void> => {
    const api = await setup(fileId);
    await vi.waitFor(() => expect(files?.update.canMove).toBe(true));
    await tick();
    const update = vi.spyOn(api.filesystem, 'updateNode');
    await openAction('Move');
    await waitForFolders();
    expect(document.querySelector('#node-update-title')?.textContent).toBe('Move “Notes.txt”');
    expect(button('Move', document.querySelector('dialog')!).disabled).toBe(true);
    expect(namedButton('Collapse Files').getAttribute('aria-expanded')).toBe('true');
    expect(namedButton('Select Projects').disabled).toBe(true);
    expect(namedButton('Select Projects').textContent).toContain('Current');
    expect(document.querySelector('button[aria-label="Expand Projects"]')).toBeNull();
    expect(document.querySelector('button[aria-label="Collapse Projects"]')).toBeNull();
    expect(document.querySelector('[aria-pressed="true"]')).toBeNull();
    expect(button('Cancel').hasAttribute('data-dialog-cancel')).toBe(true);
    expect(document.activeElement).toBe(button('Cancel'));
    expect(document.querySelector('[aria-label="Destination folders"]')?.textContent).not.toContain('Notes.txt');
    expect(document.querySelector('dialog input')).toBeNull();
    expect(document.querySelector('dialog')?.textContent).not.toContain('Retry folders');
    namedButton('Select Files').click();
    await vi.waitFor(() => expect(button('Move to “Files”').disabled).toBe(false));
    expect(namedButton('Select Files').getAttribute('aria-pressed')).toBe('true');
    button('Cancel').click();
    await tick();
    expect(document.querySelector('dialog')).toBeNull();
    expect(update).not.toHaveBeenCalled();
    expect(files?.node?.name).toBe('Notes.txt');
  });
});
