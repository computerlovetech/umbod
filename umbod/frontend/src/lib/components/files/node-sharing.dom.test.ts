import { afterEach, describe, expect, test, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import { HttpError } from '$lib/admin/infrastructure/transport';
import { InMemoryFilesApi } from '$lib/files/infrastructure/in-memory-api.test-support';
import { deferred, fileId, filesystemFixture, folderId, rootId } from '$lib/files/fixtures.test-support';
import { FilesState } from '$lib/files/state/files-state.svelte';
import { NewFolderState } from '$lib/files/state/new-folder-state.svelte';
import { UploadState } from '$lib/files/state/upload-state.svelte';
import type { NodeAccess } from '$lib/files/domain/sharing';
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

const view: NodeAccess = { node_id: fileId, revision: 'opaque', groups: [{ group_id: ' Provider Team ', permissions: ['write', 'share'] }], blocked_group_ids: ['blocked'] };
const groups = [{ group_id: ' Provider Team ', label: 'Design', description: 'Design team' }, { group_id: 'second', label: 'Readers', description: 'Project readers' }];

async function setup(id: string = folderId, configure = true): Promise<{ api: InMemoryFilesApi; state: FilesState; signIn: ReturnType<typeof vi.fn> }> {
  const api = new InMemoryFilesApi(rootId, filesystemFixture);
  if (configure) for (const node of filesystemFixture) api.sharing.configure({ ...view, node_id: node.id }, groups);
  const state = new FilesState(api);
  files = state;
  const signIn = vi.fn();
  const target = document.createElement('div');
  document.body.append(target);
  component = mount(FilesContent, { target, props: { state, folder: new NewFolderState(api, state), upload: new UploadState(api, state), signIn } });
  await state.load(id);
  await tick();
  return { api, state, signIn };
}

function button(label: string): HTMLButtonElement {
  const element = Array.from(document.querySelectorAll('button')).find((candidate) => candidate.getAttribute('aria-label') === label || candidate.textContent?.trim() === label);
  expect(element, label).toBeDefined();
  return element!;
}

async function open(label = 'Share “Notes.txt”'): Promise<void> {
  await vi.waitFor(() => expect(Array.from(document.querySelectorAll('button')).some((candidate) => candidate.getAttribute('aria-label') === label)).toBe(true));
  button(label).click();
  await vi.waitFor(() => expect(document.querySelector('input[role="combobox"]')).not.toBeNull());
  await tick();
}

async function select(label: string): Promise<void> {
  const picker = document.querySelector<HTMLInputElement>('input[role="combobox"]')!;
  picker.focus();
  picker.click();
  await tick();
  const option = Array.from(document.querySelectorAll<HTMLElement>('[role="option"]')).find((candidate) => candidate.textContent?.trim().startsWith(label));
  expect(option, label).toBeDefined();
  option!.click();
  flushSync();
  await tick();
}

async function search(query: string): Promise<HTMLInputElement> {
  const picker = document.querySelector<HTMLInputElement>('input[role="combobox"]')!;
  picker.focus();
  picker.value = query;
  picker.dispatchEvent(new Event('input', { bubbles: true }));
  flushSync();
  await tick();
  return picker;
}

function submit(): void { document.querySelector('dialog form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); }

describe('Files group sharing UI', (): void => {
  test('renders authorized current directory, directory/file rows and file details; denied defaults remain hidden', async (): Promise<void> => {
    const { state } = await setup(rootId);
    await vi.waitFor(() => expect(button('Share “Files”')).toBeDefined());
    expect(button('Share “Projects”').closest('a')).toBeNull();
    await state.load(folderId);
    await tick();
    expect(button('Share “Projects”')).toBeDefined();
    expect(button('Share “Notes.txt”').closest('tr')).not.toBeNull();
    await state.load(fileId);
    await tick();
    expect(button('Share “Notes.txt”').closest('[aria-label="File details"]')).not.toBeNull();
    state.sharing.reset();
    await tick();
    expect(document.querySelector('button[aria-label^="Share"]')).toBeNull();
  });

  test('pending and denied inspections never advertise sharing', async (): Promise<void> => {
    const { api, state } = await setup(folderId, false);
    expect(document.querySelector('button[aria-label^="Share"]')).toBeNull();
    const pending = deferred<NodeAccess>();
    vi.spyOn(api.sharing, 'inspectAccess').mockReturnValue(pending.promise);
    await state.load(fileId);
    await tick();
    expect(document.querySelector('button[aria-label^="Share"]')).toBeNull();
    pending.reject(new HttpError(403, 'Forbidden', {}));
    await tick();
    expect(document.querySelector('button[aria-label^="Share"]')).toBeNull();
  });

  test('adds, edits and removes permissions through DOM and saves exact IDs without replacing the workspace', async (): Promise<void> => {
    const { api, state } = await setup();
    const heading = document.querySelector('h1');
    const replace = vi.spyOn(api.sharing, 'replaceAccess');
    await open();
    expect(document.querySelector('dialog')?.getAttribute('aria-labelledby')).toBeTruthy();
    expect(document.querySelector('form')?.getAttribute('aria-label')).toBe('Manage group sharing');
    expect(document.querySelector('dialog')?.textContent).toContain('Design team');
    expect(document.querySelector('dialog')?.textContent).not.toContain('Discover makes this item visible');
    expect(document.querySelector('dialog')?.textContent).not.toContain('Other existing access rules');
    expect(document.querySelector('dialog')?.textContent).not.toContain('No editable group access');
    expect(document.querySelector('dialog')?.textContent).not.toContain('Only this folder is shared');
    const original = document.querySelector('section.group')!;
    expect(Array.from(original.querySelectorAll<HTMLInputElement>('input:checked')).map((input) => input.parentElement?.textContent?.trim())).toEqual(['Write', 'Manage sharing']);
    await select('Readers');
    const second = document.querySelectorAll('section.group')[1];
    expect(Array.from(second.querySelectorAll<HTMLInputElement>('input:checked')).map((input) => input.parentElement?.textContent?.trim())).toEqual(['Discover', 'Read']);
    const deletion = Array.from(second.querySelectorAll<HTMLInputElement>('input')).find((input) => input.parentElement?.textContent?.trim() === 'Delete')!;
    deletion.click();
    button('Remove Design').click();
    await tick();
    submit();
    await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
    expect(replace).toHaveBeenCalledExactlyOnceWith(fileId, 'opaque', { groups: [{ group_id: 'second', permissions: ['discover', 'read', 'delete'] }] });
    expect(document.querySelector('h1')).toBe(heading);
    expect(state.node?.id).toBe(folderId);
    expect(document.body.textContent).toContain('Sharing updated for “Notes.txt”');
  });

  test('shows matching groups directly in one custom searchable dropdown', async (): Promise<void> => {
    const { api } = await setup();
    const replace = vi.spyOn(api.sharing, 'replaceAccess');
    await open();
    expect(document.querySelector('select')).toBeNull();
    expect(document.querySelector('dialog')?.textContent).not.toContain('Find a registered group');
    const picker = await search('PROJECT');
    const list = document.querySelector('[role="listbox"]');
    expect(list?.closest('dialog')).toBe(document.querySelector('dialog'));
    expect(list?.textContent).toContain('Readers');
    expect(list?.textContent).not.toContain('Design');
    await search('missing-group');
    expect(document.querySelector('[role="listbox"]')?.textContent).toContain('No groups found');
    expect(document.querySelectorAll('[role="option"]')).toHaveLength(0);
    await search('readers');
    const enter = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
    picker.dispatchEvent(enter);
    await tick();
    expect(enter.defaultPrevented).toBe(true);
    expect(document.querySelectorAll('section.group')).toHaveLength(2);
    expect(picker.value).toBe('');
    expect(document.querySelector('[role="listbox"]')).toBeNull();
    expect(document.activeElement).toBe(picker);
    expect(replace).not.toHaveBeenCalled();
  });

  test('searches exact provider IDs and preserves them when selecting and saving', async (): Promise<void> => {
    const { api } = await setup();
    const replace = vi.spyOn(api.sharing, 'replaceAccess');
    await open();
    button('Remove Design').click();
    await tick();
    await search('provider team');
    expect(document.querySelector('[role="option"]')?.textContent?.trim()).toBe('Design');
    expect(document.querySelector('[role="listbox"]')?.textContent).not.toContain('Provider Team');
    expect(document.querySelector('[role="listbox"]')?.textContent).not.toContain('Design team');
    await select('Design');
    expect(document.querySelector('section.group')?.textContent).toContain(' Provider Team ');
    submit();
    await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
    expect(replace).toHaveBeenCalledExactlyOnceWith(fileId, 'opaque', {
      groups: [{ group_id: ' Provider Team ', permissions: ['discover', 'read'] }]
    });
  });

  test('Escape dismisses search results without dismissing the sharing dialog', async (): Promise<void> => {
    await setup();
    await open();
    const picker = await search('readers');
    const dialog = document.querySelector('dialog');
    const escape = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
    picker.dispatchEvent(escape);
    await tick();
    expect(escape.defaultPrevented).toBe(true);
    expect(document.querySelector('[role="listbox"]')).toBeNull();
    expect(document.querySelector('dialog')).toBe(dialog);
    expect(document.activeElement).toBe(picker);
  });

  test.each(['Cancel', 'Close sharing', 'escape', 'backdrop'])('dismisses by %s and restores invoking focus without mutation', async (mechanism): Promise<void> => {
    const { api } = await setup();
    const replace = vi.spyOn(api.sharing, 'replaceAccess');
    const trigger = button('Share “Notes.txt”');
    await open();
    const dialog = document.querySelector('dialog')!;
    if (mechanism === 'escape') dialog.dispatchEvent(new Event('cancel', { cancelable: true }));
    else if (mechanism === 'backdrop') dialog.dispatchEvent(new MouseEvent('click', { clientX: -10, clientY: -10, bubbles: true }));
    else button(mechanism).click();
    await tick();
    expect(document.querySelector('dialog')).toBeNull();
    await vi.waitFor(() => expect(document.activeElement).toBe(trigger));
    expect(replace).not.toHaveBeenCalled();
  });

  test('all dismissal mechanisms and double submit are blocked while saving', async (): Promise<void> => {
    const { api } = await setup();
    await open();
    const response = deferred<NodeAccess>();
    const replace = vi.spyOn(api.sharing, 'replaceAccess').mockReturnValueOnce(response.promise);
    await search('readers');
    expect(document.querySelector('[role="listbox"]')).not.toBeNull();
    submit();
    await tick();
    expect(document.querySelector('[role="listbox"]')).toBeNull();
    expect(document.querySelector<HTMLInputElement>('input[role="combobox"]')?.disabled).toBe(true);
    expect(button('Cancel').disabled).toBe(true);
    expect(button('Close sharing').disabled).toBe(true);
    const dialog = document.querySelector('dialog')!;
    dialog.dispatchEvent(new Event('cancel', { cancelable: true }));
    dialog.dispatchEvent(new MouseEvent('click', { clientX: -10, clientY: -10, bubbles: true }));
    submit();
    await tick();
    expect(document.querySelector('dialog')).toBe(dialog);
    expect(replace).toHaveBeenCalledOnce();
    response.resolve(view);
    await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
  });

  test('conflict retains draft until explicit reload and does not retry automatically', async (): Promise<void> => {
    const { api } = await setup();
    await open();
    await select('Readers');
    const replace = vi.spyOn(api.sharing, 'replaceAccess').mockRejectedValueOnce(new HttpError(412, 'Conflict', {}));
    submit();
    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toContain('Access changed elsewhere'));
    expect(document.querySelectorAll('section.group')).toHaveLength(2);
    expect(button('Save sharing').disabled).toBe(true);
    expect(replace).toHaveBeenCalledOnce();
    button('Reload latest access').click();
    await vi.waitFor(() => expect(document.querySelectorAll('section.group')).toHaveLength(1));
    expect(button('Save sharing').disabled).toBe(false);
  });

  test('fallback focus uses Files heading when invoking row disappears', async (): Promise<void> => {
    const { state } = await setup();
    await open();
    state.sharing.revoke(fileId);
    await tick();
    button('Cancel').click();
    await tick();
    await vi.waitFor(() => expect(document.activeElement).toBe(document.querySelector('#files-heading')));
  });

  test('navigation during mutation fences obsolete result, announcement and focus', async (): Promise<void> => {
    const { api, state } = await setup();
    await open();
    const response = deferred<NodeAccess>();
    vi.spyOn(api.sharing, 'replaceAccess').mockReturnValueOnce(response.promise);
    submit();
    await tick();
    await state.load(rootId);
    await tick();
    const focus = document.activeElement;
    response.resolve(view);
    await tick();
    expect(document.querySelector('dialog')).toBeNull();
    expect(document.body.textContent).not.toContain('Sharing updated');
    expect(document.activeElement).toBe(focus);
    expect(state.node?.id).toBe(rootId);
  });
});
