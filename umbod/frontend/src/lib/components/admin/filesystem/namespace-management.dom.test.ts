import { afterEach, expect, test, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import NamespaceWorkspaceTestHarness from './NamespaceWorkspaceTestHarness.test-support.svelte';
import { NamespaceManagementState } from './namespace-management-state.svelte';
import { InMemoryNamespaceAdministration } from '../../../../../tests/support/filesystem/in-memory-namespace-administration';
import type { SharedNamespace } from '#lib/admin/filesystem/domain/namespaces.js';
import { HttpError } from '#lib/admin/infrastructure/transport.js';
import { deferred } from '#lib/files/fixtures.test-support.js';
import { createWorkspace } from '../group-permissions/workspace.test-support';
import type { GroupPermissionsWorkspaceState } from '../group-permissions/group-permissions-workspace-state.svelte';

let component: ReturnType<typeof mount> | undefined;
let state: NamespaceManagementState | undefined;
let workspace: GroupPermissionsWorkspaceState | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  state?.dispose();
  workspace?.dispose();
  component = undefined;
  state = undefined;
  workspace = undefined;
  vi.restoreAllMocks();
  document.body.replaceChildren();
});

function button(label: string, scope: ParentNode = document): HTMLButtonElement {
  const result = [...scope.querySelectorAll('button')].find((entry) => entry.getAttribute('aria-label') === label || entry.textContent?.trim() === label);
  if (!result) throw new Error(`Button not found: ${label}`);
  return result;
}

function dialog(): HTMLDialogElement {
  const result = document.querySelector<HTMLDialogElement>('dialog');
  if (!result) throw new Error('Namespace dialog not found');
  return result;
}

function nameInput(): HTMLInputElement {
  const result = dialog().querySelector<HTMLInputElement>('input[name="namespace_name"]');
  if (!result) throw new Error('Namespace name input not found');
  return result;
}

function descriptionInput(): HTMLTextAreaElement {
  const result = dialog().querySelector<HTMLTextAreaElement>('textarea[name="namespace_description"]');
  if (!result) throw new Error('Namespace description input not found');
  return result;
}

function changeDescription(description: string): void {
  const input = descriptionInput();
  input.value = description;
  input.dispatchEvent(new Event('input', { bubbles: true }));
}

function changeName(name: string): void {
  const input = nameInput();
  input.value = name;
  input.dispatchEvent(new Event('input', { bubbles: true }));
}

function accessGroup(label: string): HTMLFieldSetElement {
  const group = document.querySelector<HTMLFieldSetElement>(`fieldset[aria-label="Access to ${label}"]`);
  if (!group) throw new Error(`Access group not found: ${label}`);
  return group;
}

function accessRadio(label: string, access: string): HTMLInputElement {
  const option = [...accessGroup(label).querySelectorAll('label')].find((entry) => entry.textContent?.trim() === access);
  const input = option?.querySelector<HTMLInputElement>('input[type="radio"]');
  if (!input) throw new Error(`Access option not found: ${label}, ${access}`);
  return input;
}

async function chooseAccess(label: string, access: string): Promise<void> {
  accessRadio(label, access).click();
  await tick();
}

async function renderNamespaces(api: InMemoryNamespaceAdministration, selectedGroup: () => string | null = () => 'readers'): Promise<void> {
  state = new NamespaceManagementState(api, selectedGroup);
  await state.load();
  component = mount(NamespaceWorkspaceTestHarness, { target: document.body, props: { state } });
  await tick();
}

test('shows an empty list and a labelled creation action in the page header', async (): Promise<void> => {
  await renderNamespaces(new InMemoryNamespaceAdministration([], ['readers']));
  expect(document.querySelector('ul[aria-label="Shared namespaces"]')?.textContent).toContain('No shared namespaces');
  expect(button('Save permissions').disabled).toBe(true);
  const add = button('Add Namespace');
  expect(add.textContent?.trim()).toBe('Add Namespace');
  expect(document.querySelector('.page-header .page-actions button')).toBe(add);
  expect(document.querySelector('.namespaces button')?.textContent).not.toContain('Add Namespace');
  expect(add.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true');
});

test('radio changes are local until the native save form submits and status reflects pending and saved access', async (): Promise<void> => {
  const api = new InMemoryNamespaceAdministration([], ['readers']);
  const entry = await api.create({ name: 'Research', groups: [] });
  const second = await api.create({ name: 'Archives', groups: [] });
  await renderNamespaces(api);
  const update = vi.spyOn(api, 'update');
  expect(button('Save permissions').disabled).toBe(true);
  for (const name of ['Research', 'Archives']) {
    expect(accessGroup(name).querySelector('legend')?.textContent).toBe('Access');
    expect(accessGroup(name).dataset.size).toBe('compact');
    expect([...accessGroup(name).querySelectorAll('label')].map((label) => label.textContent?.trim())).toEqual(['No access', 'Read', 'Read and write']);
    expect(accessRadio(name, 'No access').checked).toBe(true);
  }
  expect(accessRadio('Research', 'Read').name).not.toBe(accessRadio('Archives', 'Read').name);
  await chooseAccess('Research', 'Read');
  expect(accessRadio('Research', 'Read').checked).toBe(true);
  expect(accessRadio('Research', 'No access').checked).toBe(false);
  expect(accessRadio('Archives', 'No access').checked).toBe(true);
  expect(button('Save permissions').disabled).toBe(false);
  await chooseAccess('Research', 'No access');
  expect(button('Save permissions').disabled).toBe(true);
  expect(update).not.toHaveBeenCalled();
  await chooseAccess('Research', 'Read');
  await chooseAccess('Archives', 'Read and write');
  expect(accessRadio('Research', 'Read').checked).toBe(true);
  expect(accessRadio('Archives', 'Read and write').checked).toBe(true);
  expect(update).not.toHaveBeenCalled();
  expect((await api.list()).map((namespace) => namespace.groups)).toEqual([[], []]);
  expect(button('Save permissions').disabled).toBe(false);
  expect(document.querySelector('[role="status"][aria-label="Unsaved changes"]')).not.toBeNull();
  const pending = deferred<SharedNamespace>();
  update.mockReturnValueOnce(pending.promise);
  button('Save permissions').click();
  await tick();
  expect(update).toHaveBeenCalledTimes(1);
  expect(button('Save permissions').disabled).toBe(true);
  expect(document.querySelector('[role="status"][aria-label="Saving changes…"]')).not.toBeNull();
  for (const name of ['Research', 'Archives']) {
    expect(accessGroup(name).disabled).toBe(true);
    expect([...accessGroup(name).querySelectorAll<HTMLInputElement>('input[type="radio"]')].every((input) => input.disabled)).toBe(true);
  }
  const saved = { ...entry, revision: 2, groups: [{ group_id: 'readers', access: 'read' as const }] };
  pending.resolve(saved);
  await vi.waitFor(() => expect(update).toHaveBeenCalledTimes(2));
  await vi.waitFor(() => expect(button('Save permissions').disabled).toBe(true));
  expect(update).toHaveBeenNthCalledWith(1, entry.id, { name: 'Research', expected_revision: 1, groups: [{ group_id: 'readers', access: 'read' }] });
  expect(update).toHaveBeenLastCalledWith(second.id, { name: 'Archives', expected_revision: 1, groups: [{ group_id: 'readers', access: 'read_write' }] });
  expect(document.querySelector('[role="status"][aria-label="All changes saved"]')).not.toBeNull();
});

test('reload conflict recovery requires discard confirmation and cancel keeps the local access', async (): Promise<void> => {
  const api = new InMemoryNamespaceAdministration([], ['readers']);
  const entry = await api.create({ name: 'Research', groups: [] });
  await renderNamespaces(api);
  await api.update(entry.id, { name: entry.name, expected_revision: 1, groups: [{ group_id: 'readers', access: 'read_write' }] });
  await chooseAccess('Research', 'Read');
  button('Save permissions').click();
  await vi.waitFor(() => expect(button('Save permissions').disabled).toBe(true));
  const list = vi.spyOn(api, 'list');
  button('Reload namespaces').click();
  await tick();
  const warning = [...document.querySelectorAll('[role="alert"]')].find((alert) => alert.textContent?.includes('unsaved permission changes'));
  expect(warning).toBeDefined();
  button('Cancel').click();
  await tick();
  expect(list).not.toHaveBeenCalled();
  expect(accessRadio('Research', 'Read').checked).toBe(true);
  expect(button('Save permissions').disabled).toBe(true);
  button('Reload namespaces').click();
  await tick();
  button('Discard changes').click();
  await vi.waitFor(() => expect(accessRadio('Research', 'Read and write').checked).toBe(true));
  expect(list).toHaveBeenCalledTimes(1);
  expect(button('Save permissions').disabled).toBe(true);
});

test('creates and edits namespaces in feature-local modals without granting the selected group', async (): Promise<void> => {
  const api = new InMemoryNamespaceAdministration([], ['readers']);
  await renderNamespaces(api);
  button('Add Namespace').click();
  await tick();
  expect(dialog().getAttribute('aria-modal')).toBe('true');
  expect(dialog().querySelector('h2')?.textContent).toBe('New namespace');
  expect(dialog().querySelectorAll('input')).toHaveLength(1);
  expect(descriptionInput().required).toBe(false);
  expect(dialog().querySelector(`label[for="${descriptionInput().id}"]`)?.textContent).toBe('Description (optional)');
  expect(descriptionInput().getAttribute('rows')).toBe('4');
  expect(nameInput().type).toBe('text');
  expect(nameInput().autocomplete).toBe('off');
  expect(nameInput().getAttribute('data-1p-ignore')).toBe('true');
  expect(dialog().querySelector('form[aria-label="Namespace"]')).not.toBeNull();
  expect(dialog().querySelector('input[type="radio"]')).toBeNull();
  changeName('Research');
  changeDescription('<img src=x onerror=alert(1)>\nRead first');
  await tick();
  button('Create namespace').click();
  await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
  expect(await api.list()).toMatchObject([{ name: 'Research', revision: 1, groups: [] }]);
  expect(document.querySelector('.namespace-description')?.textContent).toBe('<img src=x onerror=alert(1)>\nRead first');
  expect(document.querySelector('.namespace-description img')).toBeNull();
  expect(accessRadio('Research', 'No access').checked).toBe(true);
  button('Edit Research').click();
  await tick();
  expect(dialog().querySelector('h2')?.textContent).toBe('Edit namespace');
  expect(nameInput().value).toBe('Research');
  expect(descriptionInput().value).toBe('<img src=x onerror=alert(1)>\nRead first');
  expect(nameInput().type).toBe('text');
  expect(nameInput().autocomplete).toBe('off');
  expect(nameInput().getAttribute('data-1p-ignore')).toBe('true');
  expect(dialog().querySelector('input[type="radio"]')).toBeNull();
  changeName('Archives');
  changeDescription('');
  await tick();
  button('Save changes').click();
  await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
  expect(await api.list()).toMatchObject([{ name: 'Archives', revision: 2, groups: [] }]);
  expect(button('Edit Archives')).toBeDefined();
  expect((await api.list())[0].description).toBe('');
  expect(document.querySelector('.namespace-description')).toBeNull();
  expect(document.querySelector('a[href^="/files"]')).toBeNull();
});

test('retains the groups sidebar and assigns namespace access independently for the selected group', async (): Promise<void> => {
  const api = new InMemoryNamespaceAdministration([], ['a', 'b']);
  await api.create({ name: 'Research', groups: [{ group_id: 'a', access: 'read' }, { group_id: 'b', access: 'read_write' }] });
  workspace = createWorkspace(undefined, api).state;
  workspace.activate('filesystem');
  const groupSelection = workspace;
  state = groupSelection.namespaces;
  await state.load();
  component = mount(NamespaceWorkspaceTestHarness, { target: document.body, props: { workspace, state } });
  await tick();
  const sidebar = document.querySelector('aside[aria-label="Groups"]');
  expect(sidebar).not.toBeNull();
  expect(document.querySelector('.group-header h2')?.textContent).toBe('Operators');
  expect(accessRadio('Research', 'Read').checked).toBe(true);
  const readers = [...sidebar!.querySelectorAll<HTMLButtonElement>('button')].find((entry) => entry.textContent?.includes('Readers'));
  expect(readers).toBeDefined();
  readers!.click();
  await tick();
  expect(document.querySelector('.group-header h2')?.textContent).toBe('Readers');
  expect(accessRadio('Research', 'Read and write').checked).toBe(true);
  await chooseAccess('Research', 'No access');
  button('Save permissions').click();
  await vi.waitFor(async (): Promise<void> => expect(await api.list()).toMatchObject([{ groups: [{ group_id: 'a', access: 'read' }] }]));
  expect(document.querySelector('dialog')).toBeNull();
  expect(accessRadio('Research', 'No access').checked).toBe(true);
  expect(document.querySelector('aside[aria-label="Groups"]')).toBe(sidebar);
});

test('recovers stale access separately from namespace creation and preserves other group grants', async (): Promise<void> => {
  const api = new InMemoryNamespaceAdministration([], ['readers', 'other']);
  const initial = await api.create({ name: 'Research', groups: [{ group_id: 'other', access: 'read' }] });
  await renderNamespaces(api);
  await api.update(initial.id, { name: 'Research', expected_revision: 1, groups: [{ group_id: 'other', access: 'read_write' }] });
  await chooseAccess('Research', 'Read');
  button('Save permissions').click();
  await vi.waitFor(() => expect(document.querySelector('.admin-save-action__status')?.getAttribute('aria-label')).toContain('Namespace access changed'));
  expect(document.querySelector('[role="alert"]')?.textContent).toContain('Namespace access changed. Reload and review');
  expect(accessGroup('Research').disabled).toBe(true);
  button('Add Namespace').click();
  await tick();
  expect(dialog().querySelector('[role="alert"]')).toBeNull();
  button('Cancel').click();
  await tick();
  button('Reload namespaces').click();
  await tick();
  button('Discard changes').click();
  await vi.waitFor(() => expect(accessGroup('Research').disabled).toBe(false));
  await chooseAccess('Research', 'Read');
  button('Save permissions').click();
  await vi.waitFor(async (): Promise<void> => expect((await api.list())[0].groups).toEqual([
    { group_id: 'other', access: 'read_write' }, { group_id: 'readers', access: 'read' }
  ]));
});

test('creates namespaces independently when no group exists without offering group assignment', async (): Promise<void> => {
  const api = new InMemoryNamespaceAdministration([], []);
  await api.create({ name: 'Research', groups: [] });
  await renderNamespaces(api, () => null);
  expect(document.querySelector('input[type="radio"]')).toBeNull();
  expect(button('Add Namespace').disabled).toBe(false);
  button('Add Namespace').click();
  await tick();
  changeName('Archives');
  await tick();
  button('Create namespace').click();
  await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
  expect(await api.list()).toHaveLength(2);
});

test.each(['Cancel', 'Close', 'Escape', 'backdrop'])('dismisses creation through %s and discards the unsaved name', async (dismissal: string): Promise<void> => {
  const api = new InMemoryNamespaceAdministration([], ['readers']);
  const create = vi.spyOn(api, 'create');
  await renderNamespaces(api);
  button('Add Namespace').click();
  await tick();
  changeName('Discarded draft');
  changeDescription('Discarded description');
  if (dismissal === 'Escape') dialog().dispatchEvent(new Event('cancel', { cancelable: true }));
  else if (dismissal === 'backdrop') dialog().dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: -10, clientY: -10 }));
  else button(dismissal).click();
  await tick();
  expect(document.querySelector('dialog')).toBeNull();
  expect(create).not.toHaveBeenCalled();
  button('Add Namespace').click();
  await tick();
  expect(nameInput().value).toBe('');
  expect(descriptionInput().value).toBe('');
  expect(button('Create namespace').disabled).toBe(true);
});

test('protects the name modal against dismissal and duplicate submission while saving', async (): Promise<void> => {
  const api = new InMemoryNamespaceAdministration([], ['readers']);
  const pending = deferred<SharedNamespace>();
  const create = vi.spyOn(api, 'create').mockReturnValue(pending.promise);
  await renderNamespaces(api);
  button('Add Namespace').click();
  await tick();
  changeName('Pending namespace');
  changeDescription('Pending description');
  await tick();
  button('Create namespace').click();
  await tick();
  const modal = dialog();
  expect(modal.querySelector('fieldset')?.disabled).toBe(true);
  expect(button('Cancel').disabled).toBe(true);
  expect(button('Close').disabled).toBe(true);
  button('Close').click();
  modal.dispatchEvent(new Event('cancel', { cancelable: true }));
  modal.dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: -10, clientY: -10 }));
  modal.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  await tick();
  expect(dialog()).toBe(modal);
  expect(nameInput().value).toBe('Pending namespace');
  expect(descriptionInput().value).toBe('Pending description');
  expect(descriptionInput().closest('fieldset')?.disabled).toBe(true);
  expect(create).toHaveBeenCalledTimes(1);
  pending.resolve({ id: crypto.randomUUID(), root_node_id: crypto.randomUUID(), name: 'Saved namespace', description: '', root_revision: 1, revision: 1, groups: [] });
  await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
  expect(button('Edit Saved namespace')).toBeDefined();
});

test('explains a duplicate global namespace name without creating a group-specific copy', async (): Promise<void> => {
  const api = new InMemoryNamespaceAdministration([], ['readers']);
  await api.create({ name: 'Research', groups: [] });
  await renderNamespaces(api);
  button('Add Namespace').click();
  await tick();
  changeName('Research');
  await tick();
  button('Create namespace').click();
  await vi.waitFor(() => expect(dialog().querySelector('[role="alert"]')?.textContent).toBe('A shared namespace with this name already exists.'));
  expect(nameInput().value).toBe('Research');
  expect(await api.list()).toHaveLength(1);
  button('Cancel').click();
  await tick();
  expect(document.querySelector('dialog')).toBeNull();
});

test('retains the modal and name after a failed save', async (): Promise<void> => {
  const api = new InMemoryNamespaceAdministration([], ['readers']);
  vi.spyOn(api, 'create').mockRejectedValue(new Error('Unavailable'));
  await renderNamespaces(api);
  button('Add Namespace').click();
  await tick();
  changeName('Retry draft');
  await tick();
  button('Create namespace').click();
  await vi.waitFor(() => expect(dialog().querySelector('[role="alert"]')?.textContent).toBe('Could not save shared namespace.'));
  expect(nameInput().value).toBe('Retry draft');
  expect(button('Create namespace').disabled).toBe(false);
});

test('refreshes a rename conflict without replacing another group’s concurrent access change', async (): Promise<void> => {
  const api = new InMemoryNamespaceAdministration([], ['readers']);
  const initial = await api.create({ name: 'Research', groups: [] });
  await renderNamespaces(api);
  button('Edit Research').click();
  await tick();
  changeName('My draft');
  changeDescription('My description');
  await api.update(initial.id, { name: 'Concurrent change', description: 'Concurrent description', expected_root_revision: 1, expected_revision: 1, groups: [{ group_id: 'readers', access: 'read_write' }] });
  await tick();
  button('Save changes').click();
  await vi.waitFor(() => expect(dialog().querySelector('[role="alert"]')?.textContent).toContain('Namespace changed'));
  expect(button('Save changes').disabled).toBe(true);
  button('Refresh revision').click();
  await vi.waitFor(() => expect(button('Save changes').disabled).toBe(false));
  expect(nameInput().value).toBe('My draft');
  expect(descriptionInput().value).toBe('My description');
  button('Save changes').click();
  await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
  expect(await api.list()).toMatchObject([{ name: 'My draft', description: 'My description', root_revision: 3, revision: 3, groups: [{ group_id: 'readers', access: 'read_write' }] }]);
});

test('requires confirmation and removes only the confirmed namespace after one pending request', async (): Promise<void> => {
  const api = new InMemoryNamespaceAdministration([], ['readers']);
  const target = await api.create({ name: 'Research', groups: [{ group_id: 'readers', access: 'read' }] });
  await api.create({ name: 'Archives', groups: [] });
  const remove = vi.spyOn(api, 'delete');
  await renderNamespaces(api);

  button('Delete namespace: Research').click();
  await tick();
  expect(dialog().getAttribute('role')).toBe('alertdialog');
  expect(dialog().textContent).toContain('Delete Research? Only empty namespaces can be deleted.');
  expect(state?.selected).toBe(target.id);
  button('Cancel').click();
  await tick();
  expect(document.querySelector('dialog')).toBeNull();
  expect(remove).not.toHaveBeenCalled();

  const pending = deferred<void>();
  remove.mockReturnValueOnce(pending.promise);
  button('Delete namespace: Research').click();
  await tick();
  const confirm = button('Delete namespace', dialog());
  confirm.click();
  confirm.click();
  await tick();
  expect(confirm.disabled).toBe(true);
  expect(button('Cancel').disabled).toBe(true);
  expect(button('Close').disabled).toBe(true);
  dialog().dispatchEvent(new Event('cancel', { cancelable: true }));
  expect(dialog().open).toBe(true);
  expect(button('Delete namespace: Research').disabled).toBe(true);
  expect(remove).toHaveBeenCalledExactlyOnceWith(target.id, { expected_revision: 1, expected_root_revision: 1 });

  pending.resolve();
  await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
  expect(state?.selected).toBeNull();
  expect(document.querySelector('button[aria-label="Delete namespace: Research"]')).toBeNull();
  expect(button('Delete namespace: Archives')).toBeDefined();
});

test('blocks deletion while permission edits are unsaved or being saved', async (): Promise<void> => {
  const api = new InMemoryNamespaceAdministration([], ['readers']);
  await api.create({ name: 'Research', groups: [] });
  const remove = vi.spyOn(api, 'delete');
  await renderNamespaces(api);
  await chooseAccess('Research', 'Read');
  const action = button('Delete namespace: Research');
  expect(action.disabled).toBe(true);
  action.click();
  expect(document.querySelector('dialog')).toBeNull();

  const pending = deferred<SharedNamespace>();
  const update = api.update;
  vi.spyOn(api, 'update').mockImplementationOnce(async (id, input) => {
    await pending.promise;
    return update(id, input);
  });
  button('Save permissions').click();
  await tick();
  expect(action.disabled).toBe(true);
  pending.resolve((await api.list())[0]);
  await vi.waitFor(() => expect(action.disabled).toBe(false));
  expect(remove).not.toHaveBeenCalled();
});

test('refreshes stale confirmation and requires another confirmation with both refreshed revisions', async (): Promise<void> => {
  const api = new InMemoryNamespaceAdministration([], []);
  const target = await api.create({ name: 'Research', groups: [] });
  await renderNamespaces(api);
  const list = vi.spyOn(api, 'list');
  const remove = vi.spyOn(api, 'delete');

  button('Delete namespace: Research').click();
  await tick();
  const refreshed = await api.update(target.id, {
    name: 'Updated research', groups: [], description: 'New', expected_revision: 1, expected_root_revision: 1
  });
  button('Delete namespace', dialog()).click();
  await vi.waitFor(() => expect(button('Delete namespace: Updated research').disabled).toBe(false));
  expect(document.querySelector('[role="alert"]')?.textContent).toContain('Namespace changed');
  expect(document.querySelector('dialog')).toBeNull();
  expect(list).toHaveBeenCalledTimes(1);
  expect(remove).toHaveBeenCalledExactlyOnceWith(target.id, { expected_revision: 1, expected_root_revision: 1 });

  button('Delete namespace: Updated research').click();
  await tick();
  expect(dialog().textContent).toContain('Updated research');
  button('Delete namespace', dialog()).click();
  await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
  expect(remove).toHaveBeenCalledTimes(2);
  expect(remove).toHaveBeenLastCalledWith(target.id, { expected_revision: refreshed.revision, expected_root_revision: refreshed.root_revision });
  expect(document.body.textContent).toContain('No shared namespaces');
});

test.each([
  ['filesystem_namespace_not_empty', 'still contains files or folders'],
  ['filesystem_namespace_active_uploads', 'has active uploads']
])('keeps the namespace and explains the %s blocker', async (code: string, message: string): Promise<void> => {
  const api = new InMemoryNamespaceAdministration([], []);
  await api.create({ name: 'Research', groups: [] });
  await renderNamespaces(api);
  const list = vi.spyOn(api, 'list');
  const remove = vi.spyOn(api, 'delete').mockRejectedValueOnce(new HttpError(409, 'Conflict', { detail: { code } }));
  button('Delete namespace: Research').click();
  await tick();
  button('Delete namespace', dialog()).click();
  await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toContain(message));
  expect(document.querySelector('dialog')).toBeNull();
  expect(button('Delete namespace: Research').disabled).toBe(false);
  expect(list).not.toHaveBeenCalled();
  expect(remove).toHaveBeenCalledTimes(1);
});

test('shows namespace loading failures with reload outside the name modal', async (): Promise<void> => {
  const api = new InMemoryNamespaceAdministration([], ['readers']);
  vi.spyOn(api, 'list').mockRejectedValueOnce(new Error('Unavailable'));
  await renderNamespaces(api);
  expect(document.querySelector('[role="alert"]')?.textContent).toBe('Could not load shared namespaces.');
  expect(document.querySelector('dialog')).toBeNull();
  button('Add Namespace').click();
  await tick();
  button('Cancel').click();
  await tick();
  expect(document.body.textContent).not.toContain('No shared namespaces');
  button('Reload namespaces').click();
  await vi.waitFor(() => expect(document.querySelector('[role="alert"]')).toBeNull());
  await vi.waitFor(() => expect(document.body.textContent).toContain('No shared namespaces'));
});
