import { afterEach, describe, expect, test, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import { HttpError } from '#lib/admin/infrastructure/transport.js';
import { InMemoryFilesApi } from '#lib/files/infrastructure/in-memory-api.test-support.js';
import { deferred, fileId, filesystemFixture, folderId, rootId } from '#lib/files/fixtures.test-support.js';
import { FilesState } from '#lib/files/state/files-state.svelte.js';
import { NewFolderState } from '#lib/files/state/new-folder-state.svelte.js';
import { UploadState } from '#lib/files/state/upload-state.svelte.js';
import type { NodeAccess, SharingRecipient, SharingRecipientSearchResult } from '#lib/files/domain/sharing.js';
import FilesContent from './FilesContent.svelte';
import NodeActions from './NodeActions.svelte';
import NodeSharingDialog from './NodeSharingDialog.svelte';
import { SharingEligibilityState } from '#lib/files/state/sharing-eligibility-state.svelte.js';

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

const view: NodeAccess = { node_id: fileId, revision: 'opaque', grants: [{ recipient: { type: 'group', group_id: ' Provider Team ', label: 'Design' }, recursive: false, permissions: ['write', 'share'] }, { recipient: { type: 'user', user_id: 'person-a', label: 'Hidden person' }, recursive: false, permissions: ['read'] }], blocked_recipients: [{ type: 'group', group_id: 'blocked' }, { type: 'user', user_id: 'protected-person' }] };
const recipients: SharingRecipient[] = [{ type: 'group', group_id: ' Provider Team ', label: 'Design' }, { type: 'group', group_id: 'second', label: 'Readers' }, { type: 'user', user_id: 'person-a', label: 'Hidden person' }, { type: 'user', user_id: 'person-b', label: 'New person' }];

async function setup(id: string = folderId, configure = true): Promise<{ api: InMemoryFilesApi; state: FilesState; signIn: ReturnType<typeof vi.fn>; onSharingSaved: ReturnType<typeof vi.fn> }> {
  const api = new InMemoryFilesApi(rootId, filesystemFixture);
  if (configure) for (const node of filesystemFixture) api.sharing.configure({ ...view, node_id: node.id }, recipients);
  const state = new FilesState(api);
  files = state;
  const signIn = vi.fn();
  const target = document.createElement('div');
  document.body.append(target);
  const onSharingSaved = vi.fn();
  component = mount(FilesContent, { target, props: { state, folder: new NewFolderState(api, state), upload: new UploadState(api, state), signIn, onSharingSaved } });
  await state.load(id);
  await tick();
  return { api, state, signIn, onSharingSaved };
}

function button(label: string): HTMLButtonElement {
  const element = Array.from(document.querySelectorAll('button')).find((candidate) => candidate.getAttribute('aria-label') === label || candidate.textContent?.trim() === label);
  expect(element, label).toBeDefined();
  return element!;
}

async function open(label = 'Share “Notes.txt”'): Promise<void> {
  const name = label.slice('Share '.length);
  button(`Actions for ${name}`).click();
  await tick();
  await vi.waitFor(() => expect(document.querySelector(`button[role="menuitem"][aria-label="${label}"]`)).not.toBeNull());
  button(label).click();
  await tick();
  expect(document.querySelector('[role="menu"]')).toBeNull();
  await vi.waitFor(() => expect(document.querySelector('input[role="combobox"]')).not.toBeNull());
  await tick();
}

async function select(label: string): Promise<void> {
  const picker = document.querySelector<HTMLInputElement>('input[role="combobox"]')!;
  await search(label);
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
  await vi.waitFor(() => expect(document.querySelector('dialog')?.textContent).not.toContain('Searching…'));
  return picker;
}

function submit(): void { document.querySelector('dialog form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); }

describe('Files group sharing UI', (): void => {
  test('renders truthful folder scopes, warns before widening and cancels without a write', async (): Promise<void> => {
    const { api, state } = await setup(rootId);
    const patch = vi.spyOn(api.sharing, 'replaceAccess');
    await open('Share “Projects”');
    const label = Array.from(document.querySelectorAll('label')).find((entry) => entry.textContent === 'Include contents');
    expect(label).toBeDefined();
    const checkbox = label!.querySelector('input')!;
    expect(checkbox.checked).toBe(false);
    checkbox.click();
    await tick();
    expect(document.querySelector('dialog')?.textContent).toContain('Saving will extend this sharing to existing and future contents.');
    expect(document.querySelector('dialog')?.textContent).toContain('Removing a direct grant may leave inherited access unchanged.');
    expect(patch).not.toHaveBeenCalled();
    button('Cancel').click();
    await tick();
    expect(patch).not.toHaveBeenCalled();
    expect(state.sharing.dialog.open).toBe(false);
    await open('Share “Projects”');
    const reopened = Array.from(document.querySelectorAll('label')).find((entry) => entry.textContent === 'Include contents')!.querySelector('input')!;
    expect(reopened.checked).toBe(false);
    await select('Readers');
    const scopes = Array.from(document.querySelectorAll('label')).filter((entry) => entry.textContent === 'Include contents').map((entry) => entry.querySelector('input')!.checked);
    expect(scopes).toEqual([false, true]);
  });

  test('uses the home label for the share menu item, dialog heading and saved announcement after a canonical rename', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    const home = { ...filesystemFixture[1], name: 'Renamed home' };
    api.sharing.configure({ ...view, node_id: home.id }, recipients);
    const sharing = new SharingEligibilityState(api.sharing, (node): string => node.id === home.id ? 'Files' : node.name);
    try {
      sharing.seed([{ node_id: home.id, share: true }]);
      const target = document.createElement('div');
      document.body.append(target);
      const state = new FilesState(api);
      files = state;
      component = mount(NodeActions, { target, props: { node: home, sharing, update: state.update, description: state.description, name: 'Files', signIn: vi.fn() } });
      await tick();
      button('Actions for “Files”').click();
      await tick();
      const share = button('Share “Files”');
      expect(share.getAttribute('role')).toBe('menuitem');
      share.click();
      await vi.waitFor(() => expect(sharing.dialog.phase).toBe('ready'));
      await unmount(component);
      const onSaved = vi.fn();
      component = mount(NodeSharingDialog, { target, props: { state: sharing.dialog, signIn: vi.fn(), onSaved } });
      await tick();
      expect(document.querySelector('dialog h2')?.textContent).toBe('Share “Files”');
      expect(sharing.dialog.node?.name).toBe('Renamed home');
      button('Save group sharing').click();
      await vi.waitFor(() => expect(sharing.dialog.open).toBe(false));
      expect(onSaved).toHaveBeenCalledExactlyOnceWith('Sharing updated for “Files”.');
      expect(home.name).toBe('Renamed home');
    } finally {
      sharing.dispose();
    }
  });

  test('renders authorized current directory, directory/file rows and file details; denied defaults remain hidden', async (): Promise<void> => {
    const { state } = await setup(rootId);
    expect(document.querySelector('[aria-label="Share “My files”"]')).toBeNull();
    expect(state.sharing.available(rootId)).toBe(false);
    expect(button('Actions for “Projects”').closest('tr')).not.toBeNull();
    expect(document.querySelector('tbody button[aria-label^="Share"]')).toBeNull();
    await state.load(folderId);
    await tick();
    expect(document.querySelector('[aria-label="Location actions"] button[aria-label^="Share"]')).toBeNull();
    expect(button('Actions for “Projects”').closest('[aria-label="Location actions"]')).not.toBeNull();
    expect(button('Actions for “Notes.txt”').closest('tr')).not.toBeNull();
    expect(document.querySelector('tbody button[aria-label^="Share"]')).toBeNull();
    await state.load(fileId);
    await tick();
    const trigger = button('Actions for “Notes.txt”');
    expect(trigger.closest('[aria-label="Location actions"]')).not.toBeNull();
    trigger.click();
    await tick();
    expect(button('Share “Notes.txt”').getAttribute('role')).toBe('menuitem');
    state.sharing.reset();
    await tick();
    expect(document.querySelector('button[aria-label^="Share"]')).toBeNull();
  });

  test('keeps the primary toolbar unchanged when sharing availability changes', async (): Promise<void> => {
    const { state } = await setup();
    const toolbar = document.querySelector('[aria-label="Location actions"]');
    expect(toolbar).not.toBeNull();
    const controls = [...toolbar!.querySelectorAll('button:not([role="menuitem"])')];
    expect(controls.map((control): string | null => control.getAttribute('aria-label'))).toEqual(['Upload file', 'New folder', 'Actions for “Projects”']);
    expect(toolbar!.querySelector('[aria-label^="Share"]')).toBeNull();
    state.sharing.revoke(folderId);
    await tick();
    expect([...toolbar!.querySelectorAll('button:not([role="menuitem"])')]).toEqual(controls);
    button('Actions for “Projects”').click();
    await tick();
    expect(document.querySelector('[role="menuitem"][aria-label="Share “Projects”"]')).toBeNull();
    state.sharing.seed([{ node_id: folderId, share: true }]);
    await tick();
    expect(button('Share “Projects”').getAttribute('role')).toBe('menuitem');
    expect([...toolbar!.querySelectorAll('button:not([role="menuitem"])')]).toEqual(controls);
  });

  test.each([fileId, folderId])('direct UUID %s renders shared content and sharing without namespace-root access', async (targetId): Promise<void> => {
    const nodes = filesystemFixture.map((node) => ({ ...node, visible_to: { type: 'namespace' as const, namespace_id: rootId, kind: 'personal' as const, name: 'Alex’s files' } }));
    const api = new InMemoryFilesApi(rootId, nodes, undefined, undefined, (node) => node.id !== rootId);
    vi.spyOn(api.filesystem, 'listNamespaces').mockResolvedValue([]);
    api.sharing.configure({ ...view, node_id: targetId }, recipients);
    const state = new FilesState(api);
    files = state;
    component = mount(FilesContent, { target: document.body, props: { state, folder: new NewFolderState(api, state), upload: new UploadState(api, state), signIn: vi.fn() } });
    await state.load(targetId);
    await tick();
    expect(state.phase).toBe('ready');
    expect(state.namespaces).toEqual([]);
    expect(document.querySelector('h1')?.textContent).toBe('Files');
    expect(document.querySelector('[aria-label="File namespaces"]')).toBeNull();
    const name = targetId === fileId ? 'Notes.txt' : 'Projects';
    button(`Actions for “${name}”`).click();
    await tick();
    button(`Share “${name}”`).click();
    await vi.waitFor(() => expect(state.sharing.dialog.phase).toBe('ready'));
    await tick();
    expect(document.querySelector('dialog form[aria-label="Manage sharing"]')).not.toBeNull();
    button('Close').click();
    await tick();
    expect(state.sharing.dialog.open).toBe(false);
    expect(state.node?.visible_to).toEqual({ type: 'namespace', namespace_id: rootId, kind: 'personal', name: 'Alex’s files' });
  });

  test('header sharing restores focus to its persistent ellipsis trigger', async (): Promise<void> => {
    const { api } = await setup();
    const replace = vi.spyOn(api.sharing, 'replaceAccess');
    const trigger = button('Actions for “Projects”');
    trigger.focus();
    await open('Share “Projects”');
    await vi.waitFor(() => expect(document.querySelector('input[role="combobox"]')).not.toBeNull());
    await tick();
    expect(document.activeElement).toBe(button('Close'));
    button('Close').click();
    await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
    await vi.waitFor(() => expect(document.activeElement).toBe(trigger));
    expect(replace).not.toHaveBeenCalled();
  });

  test('pending and denied inspections never advertise sharing', async (): Promise<void> => {
    const { api, state } = await setup(folderId, false);
    expect(document.querySelector('button[aria-label^="Share"]')).toBeNull();
    const pending = deferred<NodeAccess>();
    vi.spyOn(api.sharing, 'inspectAccess').mockReturnValue(pending.promise);
    await state.load(fileId);
    state.sharing.recheck(fileId);
    await tick();
    const trigger = button('Actions for “Notes.txt”');
    trigger.click();
    await tick();
    expect(document.querySelector('button[aria-label^="Share"]')).toBeNull();
    pending.reject(new HttpError(403, 'Forbidden', {}));
    await tick();
    expect(document.querySelector('button[aria-label^="Share"]')).toBeNull();
    expect(button('Actions for “Notes.txt”')).toBe(trigger);
  });

  test('adds, edits and removes permissions through DOM and saves exact IDs without replacing the workspace', async (): Promise<void> => {
    const { api, state, onSharingSaved } = await setup();
    const heading = document.querySelector('h1');
    const replace = vi.spyOn(api.sharing, 'replaceAccess');
    await open();
    expect(document.querySelector('dialog')?.getAttribute('aria-labelledby')).toBeTruthy();
    expect(document.querySelector('form')?.getAttribute('aria-label')).toBe('Manage sharing');
    expect(document.querySelector('dialog')?.textContent).toContain('Design');
    expect(document.querySelector('dialog')?.textContent).not.toContain('Hidden person');
    expect(document.querySelector('dialog')?.textContent).not.toContain('protected-person');
    expect(document.querySelector('dialog')?.textContent).not.toContain('Discover makes this item visible');
    expect(document.querySelector('dialog')?.textContent).not.toContain('Other existing access rules');
    expect(document.querySelector('dialog')?.textContent).not.toContain('No editable group access');
    expect(document.querySelector('dialog')?.textContent).not.toContain('Only this folder is shared');
    const original = document.querySelector('section.recipient')!;
    expect(Array.from(original.querySelectorAll<HTMLInputElement>('input:checked')).map((input) => input.parentElement?.textContent?.trim())).toEqual(['Write', 'Manage sharing']);
    await select('Readers');
    const second = document.querySelectorAll('section.recipient')[1];
    expect(Array.from(second.querySelectorAll<HTMLInputElement>('input:checked')).map((input) => input.parentElement?.textContent?.trim())).toEqual(['Discover', 'Read']);
    const deletion = Array.from(second.querySelectorAll<HTMLInputElement>('input')).find((input) => input.parentElement?.textContent?.trim() === 'Delete')!;
    deletion.click();
    button('Remove Design').click();
    await tick();
    submit();
    await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
    expect(replace).toHaveBeenCalledExactlyOnceWith(fileId, 'opaque', { grants: [{ recipient: { type: 'group', group_id: 'second' }, recursive: false, permissions: ['discover', 'read', 'delete'] }] }, 'group');
    expect((await api.sharing.inspectAccess(fileId, 'user')).grants).toEqual([view.grants[1]]);
    expect(document.querySelector('h1')).toBe(heading);
    expect(state.node?.id).toBe(folderId);
    expect(onSharingSaved).toHaveBeenCalledExactlyOnceWith('Sharing updated for “Notes.txt”.');
    expect(document.body.textContent).not.toContain('Sharing updated for “Notes.txt”');
  });

  test('shows matching groups directly in one custom searchable dropdown', async (): Promise<void> => {
    const { api } = await setup();
    const replace = vi.spyOn(api.sharing, 'replaceAccess');
    await open();
    expect(document.querySelector('select')).toBeNull();
    expect(document.querySelector('dialog')?.textContent).not.toContain('Find a registered group');
    const picker = await search('Readers');
    const list = document.querySelector('[role="listbox"]');
    expect(list?.closest('dialog')).toBe(document.querySelector('dialog'));
    expect(list?.textContent).toContain('Readers');
    expect(list?.textContent).not.toContain('Design');
    await search('missing-group');
    expect(document.querySelector('[role="listbox"]')?.textContent).toContain('No recipients found');
    expect(document.querySelectorAll('[role="option"]')).toHaveLength(0);
    await search('readers');
    const enter = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
    picker.dispatchEvent(enter);
    await tick();
    expect(enter.defaultPrevented).toBe(true);
    expect(document.querySelectorAll('section.recipient')).toHaveLength(2);
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
    expect(document.querySelector('[role="option"]')?.textContent?.trim()).toBe('Design ( Provider Team )');
    expect(document.querySelector('[role="listbox"]')?.textContent).toContain('Provider Team');
    expect(document.querySelector('[role="listbox"]')?.textContent).not.toContain('Design team');
    await select('Design');
    expect(document.querySelector('section.recipient')?.textContent).toContain(' Provider Team ');
    submit();
    await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
    expect(replace).toHaveBeenCalledExactlyOnceWith(fileId, 'opaque', {
      grants: [{ recipient: { type: 'group', group_id: ' Provider Team ' }, recursive: false, permissions: ['discover', 'read'] }]
    }, 'group');
  });

  test('keeps tabs, picker and current access mounted while another recipient type loads', async (): Promise<void> => {
    const { api } = await setup();
    await open();
    const dialog = document.querySelector('dialog');
    const picker = document.querySelector<HTMLInputElement>('input[role="combobox"]');
    const groupTab = button('Groups');
    const userTab = button('Users');
    const group = document.querySelector('section.recipient');
    expect(picker).not.toBeNull();
    expect(group?.getAttribute('aria-label')).toBe('Design');
    const response = deferred<NodeAccess>();
    const inspect = vi.spyOn(api.sharing, 'inspectAccess').mockReturnValueOnce(response.promise);
    userTab.focus();
    userTab.click();
    await tick();
    expect(inspect).toHaveBeenCalledWith(fileId, 'user', expect.any(AbortSignal));
    expect(document.querySelector('dialog')).toBe(dialog);
    expect(document.querySelector('input[role="combobox"]')).toBe(picker);
    expect(button('Groups')).toBe(groupTab);
    expect(button('Users')).toBe(userTab);
    expect(document.querySelector('section.recipient')).toBe(group);
    expect(picker?.disabled).toBe(true);
    expect(picker?.closest('fieldset')?.getAttribute('aria-busy')).toBe('true');
    expect(groupTab.closest('fieldset')?.disabled).toBe(true);
    expect(button('Save group sharing').disabled).toBe(true);
    response.resolve({ ...view, grants: [view.grants[1]], blocked_recipients: [view.blocked_recipients[1]] });
    await vi.waitFor(() => expect(picker?.disabled).toBe(false));
    expect(document.querySelector('input[role="combobox"]')).toBe(picker);
    expect(button('Users')).toBe(userTab);
    expect(userTab.getAttribute('aria-pressed')).toBe('true');
    expect(picker?.placeholder).toBe('Search users by name');
    expect(picker?.closest('fieldset')?.getAttribute('aria-busy')).toBe('false');
    expect(document.querySelector('section.recipient')?.getAttribute('aria-label')).toBe('Hidden person');
    expect(button('Save user sharing').disabled).toBe(false);
    expect(document.activeElement).toBe(userTab);
  });

  test('keeps one search-status row mounted between idle, loading and search results', async (): Promise<void> => {
    const { api } = await setup();
    await open();
    const status = document.querySelector('.search-status');
    expect(status).not.toBeNull();
    expect(status?.textContent).toBe('');
    const response = deferred<SharingRecipientSearchResult>();
    const lookup = vi.spyOn(api.sharing, 'searchRecipients').mockReturnValueOnce(response.promise);
    const picker = document.querySelector<HTMLInputElement>('input[role="combobox"]')!;
    picker.focus();
    picker.value = 'read';
    picker.dispatchEvent(new Event('input', { bubbles: true }));
    flushSync();
    expect(document.querySelector('.search-status')).toBe(status);
    expect(status?.textContent).toBe('Searching…');
    await vi.waitFor(() => expect(lookup).toHaveBeenCalledOnce());
    response.resolve({ recipients: [{ type: 'group', group_id: 'second', label: 'Readers' }], has_more: true });
    await vi.waitFor(() => expect(status?.textContent).toBe('Refine search for more matches.'));
    expect(document.querySelector('.search-status')).toBe(status);
    expect(document.querySelectorAll('.recipient-picker > [role="status"]')).toHaveLength(1);
    await search('missing');
    expect(document.querySelector('.search-status')).toBe(status);
    expect(status?.textContent).toBe('');
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

  test.each(['Cancel', 'Close', 'escape', 'backdrop'])('dismisses by %s and restores invoking focus without mutation', async (mechanism): Promise<void> => {
    const { api } = await setup();
    const replace = vi.spyOn(api.sharing, 'replaceAccess');
    const trigger = button('Actions for “Notes.txt”');
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
    expect(button('Close').disabled).toBe(true);
    expect(button('Groups').closest('fieldset')?.disabled).toBe(true);
    expect(button('Users').closest('fieldset')?.disabled).toBe(true);
    button('Users').click();
    expect(button('Groups').getAttribute('aria-pressed')).toBe('true');
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
    expect(document.querySelectorAll('section.recipient')).toHaveLength(2);
    expect(button('Save group sharing').disabled).toBe(true);
    expect(replace).toHaveBeenCalledOnce();
    button('Reload latest access').click();
    await vi.waitFor(() => expect(document.querySelectorAll('section.recipient')).toHaveLength(1));
    expect(button('Save group sharing').disabled).toBe(false);
  });

  test('searches and edits users through the same modal without replacing group grants', async (): Promise<void> => {
    const { api } = await setup();
    await open();
    button('Users').click();
    await vi.waitFor(() => expect(document.querySelector('section.recipient')?.textContent).toContain('Hidden person'));
    expect(button('Save user sharing')).toBeDefined();
    await select('New person');
    const added = document.querySelector('section[aria-label="New person"]')!;
    const write = Array.from(added.querySelectorAll<HTMLInputElement>('input')).find((input) => input.parentElement?.textContent?.trim() === 'Write')!;
    expect(write).toBeDefined();
    write.click();
    button('Remove Hidden person').click();
    await tick();
    const replace = vi.spyOn(api.sharing, 'replaceAccess');
    button('Save user sharing').click();
    await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
    expect(replace).toHaveBeenCalledExactlyOnceWith(fileId, 'opaque', { grants: [{ recipient: { type: 'user', user_id: 'person-b' }, recursive: false, permissions: ['discover', 'read', 'write'] }] }, 'user');
    expect((await api.sharing.inspectAccess(fileId, 'group')).grants).toEqual([view.grants[0]]);
  });

  test('dirty scope changes offer Keep editing or Discard changes', async (): Promise<void> => {
    await setup();
    await open();
    button('Remove Design').click();
    await tick();
    button('Users').click();
    await tick();
    expect(document.querySelector('[aria-label="Unsaved sharing changes"]')).not.toBeNull();
    expect(button('Save group sharing').disabled).toBe(true);
    button('Keep editing').click();
    await tick();
    expect(button('Groups').getAttribute('aria-pressed')).toBe('true');
    expect(document.querySelectorAll('section.recipient')).toHaveLength(0);
    button('Users').click();
    await tick();
    button('Discard changes').click();
    await vi.waitFor(() => expect(document.querySelector('section.recipient')?.textContent).toContain('Hidden person'));
    expect(button('Users').getAttribute('aria-pressed')).toBe('true');
    expect(button('Save user sharing').disabled).toBe(false);
  });

  test('blank search shows guidance without requesting recipients', async (): Promise<void> => {
    const { api } = await setup();
    const searchRecipients = vi.spyOn(api.sharing, 'searchRecipients');
    await open();
    const picker = await search('   ');
    picker.click();
    await tick();
    expect(document.querySelector('[role="listbox"]')?.textContent).toContain('Type a name to search');
    expect(document.querySelectorAll('[role="option"]')).toHaveLength(0);
    expect(searchRecipients).not.toHaveBeenCalled();
  });

  test('failed search leaves loaded permissions editable', async (): Promise<void> => {
    const { api } = await setup();
    await open();
    vi.spyOn(api.sharing, 'searchRecipients').mockRejectedValueOnce(new Error('offline'));
    await search('Readers');
    expect(document.querySelector('[role="alert"]')?.textContent).toContain("Couldn't search recipients");
    const read = Array.from(document.querySelectorAll<HTMLInputElement>('section.recipient input')).find((input) => input.parentElement?.textContent?.trim() === 'Read')!;
    expect(read.disabled).toBe(false);
    read.click();
    await tick();
    expect(read.checked).toBe(true);
    expect(button('Save group sharing').disabled).toBe(false);
    button('Save group sharing').click();
    await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
  });

  test('restores the row menu trigger after sharing is revoked while other actions remain', async (): Promise<void> => {
    const { state } = await setup();
    await open();
    state.sharing.revoke(fileId);
    await tick();
    button('Cancel').click();
    await tick();
    await vi.waitFor(() => expect(document.activeElement).toBe(button('Actions for “Notes.txt”')));
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
