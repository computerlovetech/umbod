import { afterEach, describe, expect, test, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import { HttpError } from '$lib/admin/infrastructure/transport';
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

async function setup(configure: (api: InMemoryFilesApi) => void = (): void => {}): Promise<{ api: InMemoryFilesApi; state: FilesState }> {
  const api = new InMemoryFilesApi(rootId, filesystemFixture);
  for (const node of filesystemFixture) api.sharing.configure({ node_id: node.id, revision: 'opaque', grants: [], blocked_recipients: [] }, []);
  configure(api);
  const state = new FilesState(api);
  files = state;
  const target = document.createElement('div');
  document.body.append(target);
  component = mount(FilesContent, { target, props: { state, folder: new NewFolderState(api, state), upload: new UploadState(api, state), signIn: vi.fn() } });
  await state.load(folderId);
  await tick();
  return { api, state };
}

function trigger(): HTMLButtonElement {
  const button = document.querySelector<HTMLButtonElement>('tbody button[aria-label="Actions for “Notes.txt”"]');
  expect(button).not.toBeNull();
  return button!;
}

async function openMenu(): Promise<void> {
  trigger().click();
  await tick();
  await vi.waitFor(() => expect(document.querySelector('[role="menu"]')).not.toBeNull());
}

function menuitem(label: string): HTMLButtonElement {
  const button = Array.from(document.querySelectorAll<HTMLButtonElement>('[role="menuitem"]')).find((candidate) => candidate.textContent?.trim() === label);
  expect(button, label).toBeDefined();
  return button!;
}

async function openDeletion(): Promise<void> {
  await openMenu();
  menuitem('Delete').click();
  await tick();
  expect(document.querySelector('[role="menu"]')).toBeNull();
  expect(document.querySelector('dialog')).not.toBeNull();
}

function dialogButton(label: string): HTMLButtonElement {
  const button = Array.from(document.querySelectorAll<HTMLButtonElement>('dialog button')).find((candidate) => candidate.textContent?.trim() === label);
  expect(button, label).toBeDefined();
  return button!;
}

describe('Files row actions menu', (): void => {
  test('closed rows expose only the ellipsis trigger and open six decorated menu entries', async (): Promise<void> => {
    await setup();
    await vi.waitFor(() => expect(files?.rowDeletion.controllers.get(fileId)?.available).toBe(true));
    const buttons = document.querySelectorAll('tbody button');
    expect(buttons).toHaveLength(1);
    expect(buttons[0]).toBe(trigger());
    expect(trigger().textContent?.trim()).toBe('');
    expect(trigger().querySelector('svg')?.getAttribute('aria-hidden')).toBe('true');
    expect(document.querySelector('tbody [aria-label="Share “Notes.txt”"]')).toBeNull();
    expect(document.querySelector('tbody [aria-label="Delete “Notes.txt”"]')).toBeNull();
    await openMenu();
    const entries = Array.from(document.querySelectorAll('[role="menuitem"]'));
    expect(entries.map((entry) => entry.textContent?.trim())).toEqual(['View details', 'Share', 'Rename', 'Edit description', 'Move', 'Delete']);
    for (const entry of entries) {
      expect(entry.querySelectorAll('svg')).toHaveLength(1);
      expect(entry.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true');
      expect(entry.querySelector('svg')?.getAttribute('focusable')).toBe('false');
    }
    expect(menuitem('Share').getAttribute('aria-label')).toBe('Share “Notes.txt”');
    expect(menuitem('Delete').getAttribute('aria-label')).toBe('Delete “Notes.txt”');
  });

  test.each(['Cancel', 'escape'])('delete dismissal by %s restores the persistent ellipsis without mutation', async (mechanism): Promise<void> => {
    const { api } = await setup();
    const remove = vi.spyOn(api.filesystem, 'deleteFile');
    const invokingButton = trigger();
    await openDeletion();
    if (mechanism === 'escape') document.querySelector('dialog')!.dispatchEvent(new Event('cancel', { cancelable: true }));
    else dialogButton('Cancel').click();
    await tick();
    expect(document.querySelector('dialog')).toBeNull();
    expect(document.querySelector('[role="menu"]')).toBeNull();
    expect(trigger()).toBe(invokingButton);
    await vi.waitFor(() => expect(document.activeElement).toBe(invokingButton));
    expect(remove).not.toHaveBeenCalled();
  });

  test('confirm deletes once and returns focus to the Files heading after removing the row', async (): Promise<void> => {
    const { api, state } = await setup();
    const remove = vi.spyOn(api.filesystem, 'deleteFile');
    await openDeletion();
    dialogButton('Delete file').click();
    await vi.waitFor(() => expect(state.children).toHaveLength(0));
    expect(remove).toHaveBeenCalledExactlyOnceWith(fileId, 1);
    expect(state.node?.id).toBe(folderId);
    expect(document.querySelector('tbody')).toBeNull();
    expect(document.body.textContent).toContain('“Notes.txt” was deleted from the workspace.');
    await vi.waitFor(() => expect(document.activeElement).toBe(document.querySelector('#files-heading')));
  });

  test('pending deletion leaves the trigger available and announces progress outside the closed menu', async (): Promise<void> => {
    const { api } = await setup();
    const response = deferred<void>();
    const remove = vi.spyOn(api.filesystem, 'deleteFile').mockReturnValueOnce(response.promise);
    await openDeletion();
    dialogButton('Delete file').click();
    await tick();
    expect(document.querySelector('dialog')).toBeNull();
    expect(document.querySelector('[role="menu"]')).toBeNull();
    expect(trigger().disabled).toBe(false);
    const status = Array.from(document.querySelectorAll('tbody [role="status"]')).find((element) => element.textContent === 'Deleting “Notes.txt”…');
    expect(status).toBeDefined();
    expect(status?.closest('[role="menu"]')).toBeNull();
    await openMenu();
    expect(menuitem('Deleting…').disabled).toBe(true);
    expect(menuitem('Deleting…').getAttribute('aria-busy')).toBe('true');
    menuitem('Deleting…').click();
    expect(remove).toHaveBeenCalledOnce();
    response.resolve();
    await vi.waitFor(() => expect(document.querySelector('tbody')).toBeNull());
  });

  test('denied delete eligibility hides Delete while retaining the other authorized actions', async (): Promise<void> => {
    const { api } = await setup((api): void => {
      const browse = api.filesystem.browse;
      vi.spyOn(api.filesystem, 'browse').mockImplementation(async (target, signal) => {
        const result = await browse(target, signal);
        return { ...result, capabilities: result.capabilities.map((capability) => ({ ...capability, delete: false })) };
      });
    });
    const remove = vi.spyOn(api.filesystem, 'deleteFile');
    await openMenu();
    expect(Array.from(document.querySelectorAll('[role="menuitem"]')).map((entry) => entry.textContent?.trim())).toEqual(['View details', 'Share', 'Rename', 'Edit description', 'Move']);
    expect(document.querySelector('[aria-label="Delete “Notes.txt”"]')).toBeNull();
    expect(remove).not.toHaveBeenCalled();
  });

  test('sharing alone keeps the row menu eligible when editing and deletion are denied', async (): Promise<void> => {
    await setup((api): void => {
      const browse = api.filesystem.browse;
      vi.spyOn(api.filesystem, 'browse').mockImplementation(async (target, signal) => {
        const result = await browse(target, signal);
        return { ...result, capabilities: result.capabilities.map((capability) => ({ ...capability, rename: false, move: false, edit_description: false, delete: false })) };
      });
    });
    expect(document.querySelectorAll('tbody button')).toHaveLength(1);
    await openMenu();
    expect(Array.from(document.querySelectorAll('[role="menuitem"]')).map((entry) => entry.textContent?.trim())).toEqual(['View details', 'Share']);
    menuitem('Share').click();
    await tick();
    expect(document.querySelector('[role="menu"]')).toBeNull();
    await vi.waitFor(() => expect(document.querySelector('dialog form[aria-label="Manage sharing"]')).not.toBeNull());
  });
});
