import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import { InMemoryGroupCatalogue } from '$lib/admin/groups/in-memory';
import type { CatalogueGroup } from '$lib/admin/groups/domain/schemas';
import GroupsManager from './GroupsManager.svelte';
import GroupsWorkspace from './GroupsWorkspace.svelte';
import { InMemoryIdentityDirectory } from '$lib/identity-directory/in-memory.test-support';
import { GroupsState } from './groups-state.svelte';

const group: CatalogueGroup = { group_id: ' claim /../ group ', label: 'Operators', description: 'Report administrators', revision: 1 };
let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
});

function button(label: string): HTMLButtonElement {
  const result = [...document.querySelectorAll('button')].find((entry) => entry.getAttribute('aria-label') === label || entry.textContent?.trim() === label);
  if (!result) throw new Error(`Button not found: ${label}`);
  return result;
}

function input(id: string, value: string): void {
  const field = document.getElementById(id) as HTMLInputElement;
  field.value = value;
  field.dispatchEvent(new Event('input', { bubbles: true }));
}

function renderGroups(directory = new InMemoryIdentityDirectory()): { api: InMemoryGroupCatalogue; state: GroupsState } {
  const api = new InMemoryGroupCatalogue([group]);
  const state = new GroupsState(api, [group], directory);
  const target = document.createElement('div');
  document.body.append(target);
  component = mount(GroupsManager, { target, props: { state } });
  flushSync();
  return { api, state };
}

describe('group management form wiring', () => {
  it('shows login-observed groups during creation and selects their exact provider values', async (): Promise<void> => {
    const value = ' / Exact Team ';
    const directory = new InMemoryIdentityDirectory({ issuer: 'issuer', claim: 'teams', groups: [{ value, first_seen_at: '2026-01-01T00:00:00Z', last_seen_at: '2026-01-01T00:00:00Z' }], has_more: false });
    const list = vi.spyOn(directory, 'list');
    const { api } = renderGroups(directory);
    expect(list).not.toHaveBeenCalled();
    button('Add Group').click();
    await vi.waitFor(() => expect(document.querySelector('.observed-groups button')?.textContent).toBe(value));
    expect(document.body.textContent).toContain('Groups observed from logins');
    (document.querySelector('.observed-groups button') as HTMLButtonElement).click();
    await tick();
    expect((document.getElementById('provider-group-id') as HTMLInputElement).value).toBe(value);
    expect(document.querySelector('.observed-groups button')?.getAttribute('aria-pressed')).toBe('true');
    input('group-label', 'Selected');
    button('Save group').click();
    await vi.waitFor(() => expect(document.querySelector('form')).toBeNull());
    expect((await api.list()).some((entry) => entry.group_id === value)).toBe(true);
    const calls = list.mock.calls.length;
    button('Edit Operators').click();
    await tick();
    expect(document.querySelector('.observed-groups')).toBeNull();
    expect((document.getElementById('provider-group-id') as HTMLInputElement).readOnly).toBe(true);
    expect(list).toHaveBeenCalledTimes(calls);
  });

  it.each(['empty', 'failed'])('keeps manual creation available with %s suggestions without an alert', async (result: string): Promise<void> => {
    const directory = new InMemoryIdentityDirectory();
    if (result === 'failed') vi.spyOn(directory, 'list').mockRejectedValue(new Error('unavailable'));
    const { api } = renderGroups(directory);
    button('Add Group').click();
    await tick();
    input('provider-group-id', ' Manual Exact ');
    input('group-label', 'Manual');
    await tick();
    expect(document.querySelector('[role="alert"]')).toBeNull();
    expect(document.body.textContent).toContain('You can enter the group ID manually.');
    expect((document.getElementById('provider-group-id') as HTMLInputElement).readOnly).toBe(false);
    expect(button('Save group').disabled).toBe(false);
    button('Save group').click();
    await vi.waitFor(() => expect(document.querySelector('form')).toBeNull());
    expect((await api.list()).some((entry) => entry.group_id === ' Manual Exact ')).toBe(true);
  });

  it('ignores obsolete suggestion responses while keeping the typed creation draft', async (): Promise<void> => {
    const directory = new InMemoryIdentityDirectory();
    type Result = Awaited<ReturnType<InMemoryIdentityDirectory['list']>>;
    const pending: Array<(value: Result) => void> = [];
    vi.spyOn(directory, 'list').mockImplementation(() => new Promise((resolve) => { pending.push(resolve); }));
    renderGroups(directory);
    button('Add Group').click();
    await tick();
    input('provider-group-id', 'new');
    input('group-label', 'Draft');
    const response = (value: string): Result => ({ issuer: 'issuer', claim: 'groups', groups: [{ value, first_seen_at: '2026-01-01T00:00:00Z', last_seen_at: '2026-01-01T00:00:00Z' }], has_more: false });
    pending[1](response('new exact'));
    await vi.waitFor(() => expect(document.querySelector('.observed-groups button')?.textContent).toBe('new exact'));
    pending[0](response('obsolete'));
    await tick();
    expect(document.querySelector('.observed-groups button')?.textContent).toBe('new exact');
    expect((document.getElementById('provider-group-id') as HTMLInputElement).value).toBe('new');
    expect((document.getElementById('group-label') as HTMLInputElement).value).toBe('Draft');
  });

  it.each(['Cancel', 'Close', 'Escape', 'backdrop'])('dismisses the creation modal through %s without creating a group', async (dismissal: string): Promise<void> => {
    const { api } = renderGroups();
    const creating = vi.spyOn(api, 'create');
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    button('Add Group').click();
    await tick();
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]')!;
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(document.getElementById(dialog.getAttribute('aria-labelledby')!)?.textContent).toBe('Create group');
    expect(dialog.querySelector('form')).not.toBeNull();
    expect((document.getElementById('provider-group-id') as HTMLInputElement).readOnly).toBe(false);
    input('provider-group-id', 'new-team');
    input('group-label', 'New team');
    if (dismissal === 'Escape') window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    else if (dismissal === 'backdrop') dialog.parentElement!.click();
    else button(dismissal).click();
    await tick();
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(creating).not.toHaveBeenCalled();
  });

  it('keeps the modal and draft protected from dismissal while saving', async (): Promise<void> => {
    const { api } = renderGroups();
    let complete!: (result: CatalogueGroup) => void;
    vi.spyOn(api, 'update').mockImplementation(() => new Promise((resolve) => { complete = resolve; }));
    button('Edit Operators').click();
    await tick();
    input('group-label', 'Pending draft');
    button('Save group').click();
    await tick();
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]')!;
    expect(dialog.querySelector('fieldset')?.disabled).toBe(true);
    expect(button('Cancel').disabled).toBe(true);
    button('Close').click();
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    dialog.parentElement!.click();
    await tick();
    expect(document.querySelector('[role="dialog"]')).toBe(dialog);
    expect((document.getElementById('group-label') as HTMLInputElement).value).toBe('Pending draft');
    complete({ ...group, label: 'Pending draft', revision: 2 });
    await vi.waitFor(() => expect(document.querySelector('[role="dialog"]')).toBeNull());
  });

  it('disposes the state owned by the workspace when unmounted during a request', async (): Promise<void> => {
    const api = new InMemoryGroupCatalogue([group]);
    let complete!: (result: CatalogueGroup) => void;
    vi.spyOn(api, 'update').mockImplementation(() => new Promise((resolve) => { complete = resolve; }));
    const eligibility = vi.spyOn(GroupsState.prototype, 'canSave', 'get');
    const target = document.createElement('div');
    document.body.append(target);
    component = mount(GroupsWorkspace, { target, props: { groups: [group], catalogue: api, directory: new InMemoryIdentityDirectory() } });
    flushSync();
    button('Edit Operators').click();
    await tick();
    input('group-label', 'Draft');
    button('Save group').click();
    await tick();
    const owned = eligibility.mock.contexts[0] as GroupsState;
    await unmount(component);
    component = undefined;
    complete({ ...group, label: 'Late response', revision: 2 });
    await tick();
    expect(document.querySelector('form')).toBeNull();
    expect(owned.groups).toEqual([group]);
    expect(owned.canSave).toBe(false);
    eligibility.mockRestore();
  });

  it('creates from labelled inputs and retains the search element on in-place success', async (): Promise<void> => {
    const { api } = renderGroups();
    const search = document.getElementById('group-search');
    button('Add Group').click();
    await tick();
    for (const id of ['provider-group-id', 'group-label', 'group-description']) expect(document.querySelector(`label[for="${id}"]`)).not.toBeNull();
    input('provider-group-id', ' /./new ');
    input('group-label', ' New label ');
    input('group-description', 'New description');
    button('Save group').click();
    await vi.waitFor(() => expect(document.querySelector('form')).toBeNull());
    expect(await api.list()).toContainEqual({ group_id: ' /./new ', label: 'New label', description: 'New description', revision: 1 });
    expect(document.body.textContent).toContain('New description');
    expect(document.getElementById('group-search')).toBe(search);
    input('group-search', 'OPERATORS');
    await tick();
    expect(document.body.textContent).not.toContain('New description');
    expect(document.body.textContent).toContain(group.description);
  });
  it('keeps immutable IDs and draft fields through stale revisions and explicit retry', async (): Promise<void> => {
    const { api } = renderGroups();
    button('Edit Operators').click();
    await tick();
    const id = document.getElementById('provider-group-id') as HTMLInputElement;
    expect(id.readOnly).toBe(true);
    expect(id.value).toBe(group.group_id);
    input('group-label', 'My draft');
    input('group-description', 'Preserved description');
    await api.update({ group_id: group.group_id, label: 'Other draft', description: '', expected_revision: 1 });
    button('Save group').click();
    await vi.waitFor(() => expect(document.querySelector('[role="dialog"] [role="alert"]')?.textContent).toContain('changed elsewhere'));
    expect((document.getElementById('group-label') as HTMLInputElement).value).toBe('My draft');
    expect(button('Save group').disabled).toBe(true);
    button('Reload latest revision').click();
    await vi.waitFor(() => expect(button('Save group').disabled).toBe(false));
    expect((document.getElementById('group-description') as HTMLTextAreaElement).value).toBe('Preserved description');
    button('Save group').click();
    await vi.waitFor(() => expect(document.querySelector('form')).toBeNull());
    expect(await api.list()).toEqual([{ ...group, label: 'My draft', description: 'Preserved description', revision: 3 }]);
  });
  it('dispatches deletion only after confirmation and keeps injected state ownership outside rendering', async (): Promise<void> => {
    const { api, state } = renderGroups();
    const deleting = vi.spyOn(api, 'delete');
    button('Delete Operators').click();
    await tick();
    expect(deleting).not.toHaveBeenCalled();
    button('Cancel').click();
    await tick();
    button('Edit Operators').click();
    await tick();
    let complete!: (result: CatalogueGroup) => void;
    const updating = vi.spyOn(api, 'update').mockImplementation(() => new Promise((resolve) => { complete = resolve; }));
    input('group-label', 'Draft');
    button('Save group').click();
    await tick();
    expect(document.querySelector<HTMLButtonElement>('[role="dialog"] button[type="submit"]')?.disabled).toBe(true);
    expect(updating).toHaveBeenCalledTimes(1);
    await unmount(component!);
    component = undefined;
    complete({ ...group, label: 'Late response', revision: 2 });
    await tick();
    expect(state.groups).toEqual([{ ...group, label: 'Late response', revision: 2 }]);
  });
});
