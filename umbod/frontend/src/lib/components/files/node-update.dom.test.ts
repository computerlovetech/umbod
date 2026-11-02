import { afterEach, describe, expect, test, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import { HttpError } from '$lib/admin/infrastructure/transport';
import type { NodeSummary } from '$lib/files/domain/schemas';
import { deferred, fileId, filesystemFixture, folderId, rootId } from '$lib/files/fixtures.test-support';
import { InMemoryFilesApi } from '$lib/files/infrastructure/in-memory-api.test-support';
import { FilesState } from '$lib/files/state/files-state.svelte';
import { NewFolderState } from '$lib/files/state/new-folder-state.svelte';
import { UploadState } from '$lib/files/state/upload-state.svelte';
import FilesContent from './FilesContent.svelte';

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

async function openAction(label: string): Promise<void> {
  document.querySelector<HTMLButtonElement>('.heading-identity button[aria-haspopup="menu"]')!.click();
  await tick();
  button(label).click();
  await tick();
}

async function setup(id: string | null, writable = true): Promise<InMemoryFilesApi> {
  const api = new InMemoryFilesApi(rootId, filesystemFixture, undefined, undefined, undefined, () => writable);
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
    await vi.waitFor(() => expect(files?.rowEditing.controllers.get(fileId)?.update.loading).toBe(false));
    await tick();
    const destination = document.querySelector<HTMLInputElement>('#move-folder-id')!;
    destination.value = rootId;
    destination.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();
    button('Open folder ID').click();
    await vi.waitFor(() => expect(files?.rowEditing.controllers.get(fileId)?.update.canSubmit).toBe(true));
    await tick();
    button('Move here').click();
    await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
    expect((await api.filesystem.getNode(fileId)).parent_id).toBe(rootId);
    expect(document.querySelector('tbody')).toBeNull();
    expect(document.activeElement).toBe(document.querySelector('h1'));
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

  test('uses directory picker, direct ID navigation and cancellation without mutation', async (): Promise<void> => {
    const api = await setup(fileId);
    await vi.waitFor(() => expect(files?.update.canMove).toBe(true));
    await tick();
    const update = vi.spyOn(api.filesystem, 'updateNode');
    await openAction('Move');
    await vi.waitFor(() => expect(files?.update.loading).toBe(false));
    await tick();
    expect(button('Move here').disabled).toBe(true);
    expect(button('Cancel').hasAttribute('data-dialog-cancel')).toBe(true);
    expect(document.activeElement).toBe(button('Cancel'));
    expect(document.querySelector('[aria-label="Destination folders"]')?.textContent).not.toContain('Notes.txt');
    const id = document.querySelector<HTMLInputElement>('#move-folder-id')!;
    id.value = rootId;
    id.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();
    button('Open folder ID').click();
    await vi.waitFor(() => expect(files?.update.canSubmit).toBe(true));
    await tick();
    expect(button('Move here').disabled).toBe(false);
    button('Cancel').click();
    await tick();
    expect(document.querySelector('dialog')).toBeNull();
    expect(update).not.toHaveBeenCalled();
    expect(files?.node?.name).toBe('Notes.txt');
  });
});
