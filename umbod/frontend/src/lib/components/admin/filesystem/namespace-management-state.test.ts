import { resolveWorkspaceAccess } from '$lib/workspace/admin-access';
import { InMemoryWorkspaceApi } from '$lib/workspace/in-memory-api.test-support';
import { describe, expect, test, vi } from 'vitest';
import { HttpError } from '$lib/admin/infrastructure/transport';
import { InMemoryNamespaceAdministration } from '../../../../../tests/support/filesystem/in-memory-namespace-administration';
import type { NamespaceAdministration } from '$lib/admin/filesystem/namespaces-port';
import type { SharedNamespace } from '$lib/admin/filesystem/domain/namespaces';
import { deferred } from '$lib/files/fixtures.test-support';
import { NamespaceManagementState } from './namespace-management-state.svelte';

type Fixture = {
  memory: InMemoryNamespaceAdministration;
  api: NamespaceAdministration;
  state: NamespaceManagementState;
  initial: SharedNamespace;
  selection: { id: string | null };
};

async function createFixture(): Promise<Fixture> {
  const memory = new InMemoryNamespaceAdministration([], ['readers', 'writers']);
  const initial = await memory.create({ name: 'Research', groups: [{ group_id: 'readers', access: 'read' }, { group_id: 'writers', access: 'read_write' }] });
  const api: NamespaceAdministration = { list: memory.list, create: memory.create, update: memory.update };
  const selection: { id: string | null } = { id: 'readers' };
  const state = new NamespaceManagementState(api, () => selection.id);
  await state.load();
  return { memory, api, state, initial, selection };
}

describe('shared namespace name management', () => {
  test.each(['', 'What to read\nAnd when'])('creates optional descriptions independently of group selection: %s', async (description): Promise<void> => {
    const { state, api, memory } = await createFixture();
    const create = vi.fn(memory.create);
    api.create = create;
    state.beginCreate();
    state.changeName('Described');
    state.changeDescription(description);
    await state.save();
    expect(create).toHaveBeenCalledExactlyOnceWith({ name: 'Described', groups: [], ...(description ? { description } : {}) });
    expect(state.namespaces.find((entry) => entry.name === 'Described')?.description).toBe(description);
    expect(state.description).toBe('');
    state.changeDescription('Ignored');
    expect(state.description).toBe('');
    state.dispose();
  });

  test('populates, edits and clears descriptions with the selected root revision', async (): Promise<void> => {
    const { state, initial, api, memory } = await createFixture();
    const update = vi.fn(memory.update);
    api.update = update;
    state.beginEdit(initial.id);
    expect(state.description).toBe(initial.description);
    state.changeDescription('Read first');
    await state.save();
    state.beginEdit(initial.id);
    expect(state.description).toBe('Read first');
    state.changeDescription('');
    await state.save();
    expect(update).toHaveBeenLastCalledWith(initial.id, { name: initial.name, groups: initial.groups, description: '', expected_revision: 2, expected_root_revision: 2 });
    expect(state.namespaces[0]).toMatchObject({ description: '', root_revision: 3 });
    state.beginEdit(initial.id);
    state.changeDescription('Discard');
    state.closeEditor();
    expect(state.description).toBe('');
    state.dispose();
  });

  test('access-only saves omit descriptions and root revisions after an ordinary root edit', async (): Promise<void> => {
    const { state, initial, api } = await createFixture();
    const canonical = { ...initial, description: 'Edited in Files', root_revision: 5 };
    const memory = new InMemoryNamespaceAdministration([canonical], ['readers', 'writers']);
    const update = vi.fn(memory.update);
    api.update = update;
    state.stageAccess(initial.id, 'none');
    await state.savePermissions();
    expect(update).toHaveBeenCalledExactlyOnceWith(initial.id, { name: initial.name, expected_revision: 1, groups: [{ group_id: 'writers', access: 'read_write' }] });
    expect(state.namespaces[0]).toMatchObject({ description: 'Edited in Files', root_revision: 5, groups: [{ group_id: 'writers', access: 'read_write' }] });
    state.dispose();
  });

  test('refreshes both revision tokens without replacing name or description drafts', async (): Promise<void> => {
    const { state, initial, api } = await createFixture();
    state.beginEdit(initial.id);
    state.changeName('Draft name');
    state.changeDescription('Draft description');
    const concurrent = { ...initial, description: 'Concurrent root edit', root_revision: 4, revision: 3, groups: [{ group_id: 'writers', access: 'read' as const }] };
    const memory = new InMemoryNamespaceAdministration([concurrent], ['readers', 'writers']);
    api.list = memory.list;
    api.update = memory.update;
    await state.save();
    expect(state.conflict).toBe(true);
    await state.refreshConflict();
    expect(state.name).toBe('Draft name');
    expect(state.description).toBe('Draft description');
    await state.save();
    expect(state.namespaces).toMatchObject([{ name: 'Draft name', description: 'Draft description', revision: 4, root_revision: 5, groups: concurrent.groups }]);
    state.dispose();
  });

  test('root-only revision conflicts retain the local description', async (): Promise<void> => {
    const { state, initial, api } = await createFixture();
    state.beginEdit(initial.id);
    state.changeDescription('Local');
    const memory = new InMemoryNamespaceAdministration([{ ...initial, description: 'Root edit', root_revision: 2 }], ['readers', 'writers']);
    api.update = memory.update;
    api.list = memory.list;
    await state.save();
    expect(state.conflict).toBe(true);
    expect(state.description).toBe('Local');
    await state.refreshConflict();
    await state.save();
    expect(state.namespaces[0]).toMatchObject({ description: 'Local', root_revision: 3 });
    state.dispose();
  });

  test('starts and loads closed without a draft and ignores closed-editor changes', async (): Promise<void> => {
    const memory = new InMemoryNamespaceAdministration([], []);
    const state = new NamespaceManagementState(memory, () => null);
    expect(state.editorOpen).toBe(false);
    expect(state.canSave).toBe(false);
    await memory.create({ name: 'Research', groups: [] });
    await state.load();
    state.changeName('Ignored');
    await state.save();
    expect(state.editorOpen).toBe(false);
    expect(state.selected).toBeNull();
    expect(state.name).toBe('');
    expect(state.canSave).toBe(false);
    expect(state.namespaces).toMatchObject([{ name: 'Research', groups: [] }]);
    state.dispose();
  });

  test('opens only valid entries and cancels edits without writing', async (): Promise<void> => {
    const { state, initial, memory } = await createFixture();
    state.beginEdit('unknown');
    expect(state.editorOpen).toBe(false);
    state.beginEdit(initial.id);
    expect(state.editorOpen).toBe(true);
    expect(state.selected).toBe(initial.id);
    expect(state.name).toBe('Research');
    state.changeName('Unwritten');
    state.beginEdit('unknown');
    expect(state.name).toBe('Unwritten');
    state.closeEditor();
    expect(state.editorOpen).toBe(false);
    expect(state.selected).toBeNull();
    expect(state.name).toBe('');
    expect(state.canSave).toBe(false);
    expect(await memory.list()).toEqual([initial]);
    state.beginEdit(initial.id);
    expect(state.name).toBe('Research');
    state.beginCreate();
    expect(state.editorOpen).toBe(true);
    expect(state.selected).toBeNull();
    expect(state.name).toBe('');
    expect(state.canSave).toBe(false);
    state.dispose();
  });

  test.each(['readers', null])('creates name-only namespaces with empty grants when selected group is %s', async (groupId): Promise<void> => {
    const { state, api, memory, selection } = await createFixture();
    selection.id = groupId;
    const create = vi.fn(memory.create);
    api.create = create;
    state.beginCreate();
    expect(state.canAssignAccess).toBe(false);
    state.changeName('');
    expect(state.canSave).toBe(false);
    state.changeName('Archives');
    expect(state.canSave).toBe(true);
    await state.save();
    expect(create).toHaveBeenCalledExactlyOnceWith({ name: 'Archives', groups: [] });
    expect(state.namespaces.map((entry) => entry.name)).toEqual(['Archives', 'Research']);
    expect(state.editorOpen).toBe(false);
    expect(state.selected).toBeNull();
    expect(state.name).toBe('');
    expect(state.canSave).toBe(false);
    expect(state.selectedGroupId).toBe(groupId);
    state.dispose();
  });

  test('rename preserves every grant and reconciles the authoritative namespace', async (): Promise<void> => {
    const { state, initial, api, memory } = await createFixture();
    const update = vi.fn(memory.update);
    api.update = update;
    state.beginEdit(initial.id);
    state.changeName('Archives');
    await state.save();
    expect(update).toHaveBeenCalledExactlyOnceWith(initial.id, { name: 'Archives', description: '', groups: initial.groups, expected_revision: 1, expected_root_revision: 1 });
    expect(state.namespaces).toEqual([{ ...initial, name: 'Archives', revision: 2 }]);
    expect(state.editorOpen).toBe(false);
    expect(state.name).toBe('');
    state.dispose();
  });

  test('pending name saves block duplicates, cancellation, replacement and access writes', async (): Promise<void> => {
    const { state, initial, api, memory } = await createFixture();
    const pending = deferred<SharedNamespace>();
    const create = vi.fn(() => pending.promise);
    const update = vi.fn(memory.update);
    api.create = create;
    api.update = update;
    state.beginCreate();
    state.changeName('Draft');
    const saving = state.save();
    expect(state.busy).toBe(true);
    expect(state.canSave).toBe(false);
    await state.save();
    state.stageAccess(initial.id, 'read_write');
    await state.savePermissions();
    state.closeEditor();
    state.beginCreate();
    state.beginEdit(initial.id);
    state.changeName('Ignored');
    expect(create).toHaveBeenCalledExactlyOnceWith({ name: 'Draft', groups: [] });
    expect(update).not.toHaveBeenCalled();
    expect(state.editorOpen).toBe(true);
    expect(state.selected).toBeNull();
    expect(state.name).toBe('Draft');
    const authoritative = await memory.create({ name: 'Authoritative', groups: [] });
    pending.resolve(authoritative);
    await saving;
    expect(state.namespaces).toEqual([authoritative, initial]);
    expect(state.busy).toBe(false);
    expect(state.editorOpen).toBe(false);
    expect(state.name).toBe('');
    state.dispose();
  });

  test.each(['create', 'update'] as const)('%s failures retain the open name draft and cancellation clears the error', async (operation): Promise<void> => {
    const { state, initial, api, memory } = await createFixture();
    if (operation === 'create') api.create = vi.fn(memory.create).mockRejectedValueOnce(new Error('Unavailable'));
    else api.update = vi.fn(memory.update).mockRejectedValueOnce(new Error('Unavailable'));
    if (operation === 'create') state.beginCreate();
    else state.beginEdit(initial.id);
    state.changeName('My draft');
    await state.save();
    expect(state.editorOpen).toBe(true);
    expect(state.name).toBe('My draft');
    expect(state.error).toBe('Could not save shared namespace.');
    expect(state.conflict).toBe(false);
    expect(state.canSave).toBe(true);
    expect(await memory.list()).toEqual([initial]);
    state.closeEditor();
    expect(state.editorOpen).toBe(false);
    expect(state.name).toBe('');
    expect(state.error).toBe('');
    state.dispose();
  });

  test('rename conflict refresh retains the local name and preserves concurrent grants on retry', async (): Promise<void> => {
    const { state, initial, memory } = await createFixture();
    state.beginEdit(initial.id);
    state.changeName('My draft');
    const concurrent = await memory.update(initial.id, { expected_revision: 1, name: 'Concurrent', groups: [{ group_id: 'writers', access: 'read' }] });
    await state.save();
    expect(state.conflict).toBe(true);
    expect(state.editorOpen).toBe(true);
    expect(state.canSave).toBe(false);
    expect(state.name).toBe('My draft');
    await state.save();
    expect(await memory.list()).toEqual([concurrent]);
    await state.refreshConflict();
    expect(state.editorOpen).toBe(true);
    expect(state.canSave).toBe(true);
    expect(state.name).toBe('My draft');
    expect(state.error).toBe('');
    expect(state.namespaces).toEqual([concurrent]);
    await state.save();
    expect(await memory.list()).toEqual([{ ...concurrent, revision: 3, name: 'My draft' }]);
    expect(state.editorOpen).toBe(false);
    expect(state.conflict).toBe(false);
    state.dispose();
  });

  test('refresh failures retain the conflicted draft and pending refresh blocks cancellation', async (): Promise<void> => {
    const { state, api, initial, memory } = await createFixture();
    state.beginEdit(initial.id);
    state.changeName('Local draft');
    await memory.update(initial.id, { expected_revision: 1, name: 'Concurrent', groups: [] });
    await state.save();
    api.list = async (): Promise<SharedNamespace[]> => { throw new Error('Unavailable'); };
    await state.refreshConflict();
    expect(state.editorOpen).toBe(true);
    expect(state.conflict).toBe(true);
    expect(state.name).toBe('Local draft');
    expect(state.error).toBe('Could not refresh shared namespaces.');
    const pending = deferred<SharedNamespace[]>();
    api.list = () => pending.promise;
    const refreshing = state.refreshConflict();
    state.closeEditor();
    state.changeName('Ignored');
    expect(state.editorOpen).toBe(true);
    expect(state.busy).toBe(true);
    expect(state.name).toBe('Local draft');
    pending.resolve(await memory.list());
    await refreshing;
    expect(state.name).toBe('Local draft');
    expect(state.canSave).toBe(true);
    state.dispose();
  });

  test('beginCreate clears rename conflict and its error', async (): Promise<void> => {
    const { state, initial, memory } = await createFixture();
    state.beginEdit(initial.id);
    await memory.update(initial.id, { expected_revision: 1, name: 'Concurrent', groups: [] });
    await state.save();
    expect(state.conflict).toBe(true);
    state.beginCreate();
    expect(state.editorOpen).toBe(true);
    expect(state.selected).toBeNull();
    expect(state.name).toBe('');
    expect(state.conflict).toBe(false);
    expect(state.error).toBe('');
    state.dispose();
  });
});

describe('shared namespace access management', () => {
  test('reads grants from authoritative namespaces and the current externally owned group', async (): Promise<void> => {
    const { state, initial, selection } = await createFixture();
    expect(state.selectedGroupId).toBe('readers');
    expect(state.access(initial.id)).toBe('read');
    selection.id = 'writers';
    expect(state.selectedGroupId).toBe('writers');
    expect(state.access(initial.id)).toBe('read_write');
    selection.id = 'unknown';
    expect(state.access(initial.id)).toBe('none');
    expect(state.access('unknown')).toBe('none');
    selection.id = null;
    expect(state.selectedGroupId).toBeNull();
    expect(state.access(initial.id)).toBe('none');
    expect(state.canAssignAccess).toBe(false);
    state.dispose();
  });

  test('replaces and revokes only the selected group grant while preserving the name and all other grants', async (): Promise<void> => {
    const { state, initial, api, memory, selection } = await createFixture();
    const update = vi.fn(memory.update);
    api.update = update;
    state.stageAccess(initial.id, 'read_write');
    await state.savePermissions();
    expect(update).toHaveBeenLastCalledWith(initial.id, { name: initial.name, expected_revision: 1, groups: [{ group_id: 'writers', access: 'read_write' }, { group_id: 'readers', access: 'read_write' }] });
    expect(state.access(initial.id)).toBe('read_write');
    expect(state.editorOpen).toBe(false);
    state.stageAccess(initial.id, 'none');
    await state.savePermissions();
    expect(update).toHaveBeenLastCalledWith(initial.id, { name: initial.name, expected_revision: 2, groups: [{ group_id: 'writers', access: 'read_write' }] });
    expect(state.access(initial.id)).toBe('none');
    expect(state.namespaces).toEqual(await memory.list());
    expect(selection.id).toBe('readers');
    state.stageAccess(initial.id, 'read');
    await state.savePermissions();
    expect(state.access(initial.id)).toBe('read');
    expect(state.namespaces[0].groups).toEqual([{ group_id: 'writers', access: 'read_write' }, { group_id: 'readers', access: 'read' }]);
    state.dispose();
  });

  test('unchanged, invalid, missing-namespace, no-group and open-editor requests never write', async (): Promise<void> => {
    const { state, initial, api, memory, selection } = await createFixture();
    const update = vi.fn(memory.update);
    api.update = update;
    state.stageAccess(initial.id, 'read');
    await state.savePermissions();
    selection.id = 'unassigned';
    state.stageAccess(initial.id, 'none');
    await state.savePermissions();
    selection.id = 'readers';
    state.stageAccess(initial.id, 'invalid');
    await state.savePermissions();
    state.stageAccess('unknown', 'read_write');
    await state.savePermissions();
    selection.id = null;
    state.stageAccess(initial.id, 'read_write');
    await state.savePermissions();
    selection.id = 'readers';
    state.beginCreate();
    expect(state.canAssignAccess).toBe(false);
    state.stageAccess(initial.id, 'read_write');
    await state.savePermissions();
    expect(update).not.toHaveBeenCalled();
    expect(state.busy).toBe(false);
    expect(state.error).toBe('');
    state.dispose();
  });

  test('pending access writes capture the original group and preserve later selection changes', async (): Promise<void> => {
    const { state, initial, api, selection } = await createFixture();
    const pending = deferred<SharedNamespace>();
    const update = vi.fn(() => pending.promise);
    api.update = update;
    state.stageAccess(initial.id, 'none');
    const saving = state.savePermissions();
    expect(state.busy).toBe(true);
    expect(state.canAssignAccess).toBe(false);
    expect(state.selectedGroupId).toBe('readers');
    selection.id = 'writers';
    state.stageAccess(initial.id, 'none');
    await state.savePermissions();
    state.beginCreate();
    state.beginEdit(initial.id);
    expect(state.editorOpen).toBe(false);
    expect(update).toHaveBeenCalledExactlyOnceWith(initial.id, { name: initial.name, expected_revision: 1, groups: [{ group_id: 'writers', access: 'read_write' }] });
    const authoritative: SharedNamespace = { ...initial, name: 'Authoritative', revision: 2, groups: [{ group_id: 'writers', access: 'read_write' }] };
    pending.resolve(authoritative);
    await saving;
    expect(state.namespaces).toEqual([authoritative]);
    expect(state.selectedGroupId).toBe('writers');
    expect(state.access(initial.id)).toBe('read_write');
    expect(state.editorOpen).toBe(false);
    expect(state.busy).toBe(false);
    expect(state.canAssignAccess).toBe(true);
    state.dispose();
  });

  test('ordinary access failures keep authoritative grants and allow retry', async (): Promise<void> => {
    const { state, initial, api, memory } = await createFixture();
    api.update = vi.fn(memory.update).mockRejectedValueOnce(new Error('Unavailable'));
    state.stageAccess(initial.id, 'none');
    await state.savePermissions();
    expect(state.permissionFeedback.message).toBe('Could not save namespace access. Unsaved changes remain.');
    expect(state.conflict).toBe(false);
    expect(state.editorOpen).toBe(false);
    expect(state.access(initial.id)).toBe('none');
    expect(state.namespaces[0].groups).toEqual(initial.groups);
    expect(state.canAssignAccess).toBe(true);
    state.stageAccess(initial.id, 'none');
    await state.savePermissions();
    expect(state.error).toBe('');
    expect(state.access(initial.id)).toBe('none');
    state.dispose();
  });

  test('access conflicts lock policy writes across group changes and name edits until explicit reload', async (): Promise<void> => {
    const { state, initial, api, memory, selection } = await createFixture();
    const concurrent = await memory.update(initial.id, { name: initial.name, expected_revision: 1, groups: [{ group_id: 'readers', access: 'read_write' }] });
    const update = vi.fn(memory.update);
    api.update = update;
    state.stageAccess(initial.id, 'none');
    await state.savePermissions();
    expect(state.permissionFeedback.message).toBe('Namespace access changed. Reload and review before trying again.');
    expect(state.needsReload).toBe(true);
    expect(state.conflict).toBe(false);
    expect(state.canAssignAccess).toBe(false);
    selection.id = 'writers';
    state.stageAccess(initial.id, 'read');
    await state.savePermissions();
    state.beginCreate();
    state.closeEditor();
    state.beginEdit(initial.id);
    state.closeEditor();
    expect(state.error).toBe('');
    expect(state.needsReload).toBe(true);
    expect(state.canAssignAccess).toBe(false);
    state.stageAccess(initial.id, 'read');
    await state.savePermissions();
    expect(update).toHaveBeenCalledTimes(1);
    await state.load();
    expect(state.namespaces).toEqual([concurrent]);
    expect(state.needsReload).toBe(false);
    expect(state.canAssignAccess).toBe(true);
    expect(state.error).toBe('');
    state.stageAccess(initial.id, 'read');
    await state.savePermissions();
    expect(state.access(initial.id)).toBe('read');
    expect(state.namespaces[0].groups).toEqual([{ group_id: 'readers', access: 'read_write' }, { group_id: 'writers', access: 'read' }]);
    state.dispose();
  });

  test('disposal clears the reload requirement after an access conflict', async (): Promise<void> => {
    const { state, initial, api } = await createFixture();
    api.update = async (): Promise<SharedNamespace> => { throw new HttpError(409, 'Conflict', {}); };
    state.stageAccess(initial.id, 'none');
    await state.savePermissions();
    expect(state.needsReload).toBe(true);
    state.dispose();
    expect(state.needsReload).toBe(false);
    expect(state.canAssignAccess).toBe(false);
    expect(state.error).toBe('');
  });

  test('successful name saves do not clear the access conflict lock', async (): Promise<void> => {
    const { state, initial, api, memory } = await createFixture();
    api.update = vi.fn(memory.update).mockRejectedValueOnce(new HttpError(409, 'Conflict', {}));
    state.stageAccess(initial.id, 'none');
    await state.savePermissions();
    state.beginCreate();
    state.changeName('Archives');
    await state.save();
    expect(state.editorOpen).toBe(false);
    expect(state.canAssignAccess).toBe(false);
    state.beginEdit(initial.id);
    state.changeName('Renamed');
    await state.save();
    expect(state.editorOpen).toBe(false);
    expect(state.canAssignAccess).toBe(false);
    expect(state.namespaces.find((entry) => entry.id === initial.id)?.groups).toEqual(initial.groups);
    state.dispose();
  });

  test('successful namespace refresh preserves the access lock and preserves fresh grants during rename', async (): Promise<void> => {
    const { state, initial, memory } = await createFixture();
    await memory.update(initial.id, { name: 'Concurrent', expected_revision: 1, groups: [{ group_id: 'writers', access: 'read' }] });
    state.stageAccess(initial.id, 'none');
    await state.savePermissions();
    state.beginEdit(initial.id);
    state.changeName('Local name');
    await state.save();
    expect(state.conflict).toBe(true);
    await state.refreshConflict();
    await state.save();
    expect(state.canAssignAccess).toBe(false);
    expect(state.namespaces).toMatchObject([{ name: 'Local name', revision: 3, groups: [{ group_id: 'writers', access: 'read' }] }]);
    state.dispose();
  });
});

describe('drafted namespace permissions', () => {
  test('stages without HTTP, overlays only the selected group and removes reverted drafts', async (): Promise<void> => {
    const { state, api, initial, selection, memory } = await createFixture();
    const update = vi.fn(memory.update);
    api.update = update;
    state.stageAccess(initial.id, 'none');
    expect(state.access(initial.id)).toBe('none');
    expect(state.namespaces).toEqual([initial]);
    expect(state.hasUnsavedChanges).toBe(true);
    expect(state.permissionFeedback.message).toBe('Unsaved changes');
    selection.id = 'writers';
    expect(state.access(initial.id)).toBe('read_write');
    expect(state.canSavePermissions).toBe(false);
    await state.savePermissions();
    selection.id = 'readers';
    state.stageAccess(initial.id, 'read');
    expect(state.hasUnsavedChanges).toBe(false);
    await state.savePermissions();
    expect(update).not.toHaveBeenCalled();
    state.dispose();
  });

  test('one save writes only changed namespaces for the captured group and keeps descriptions', async (): Promise<void> => {
    const { state, api, initial, selection, memory } = await createFixture();
    const second = await memory.create({ name: 'Archives', description: 'Keep this', groups: [] });
    await memory.create({ name: 'Untouched', groups: [] });
    await state.load();
    const update = vi.fn(memory.update);
    api.update = update;
    state.stageAccess(initial.id, 'none');
    state.stageAccess(second.id, 'read');
    selection.id = 'writers';
    state.stageAccess(second.id, 'read_write');
    selection.id = 'readers';
    await state.savePermissions();
    expect(update).toHaveBeenCalledTimes(2);
    expect(state.namespaces.find((entry) => entry.id === second.id)).toMatchObject({ description: 'Keep this', groups: [{ group_id: 'readers', access: 'read' }] });
    expect(state.selectedGroupDirty).toBe(false);
    expect(state.hasUnsavedChanges).toBe(true);
    selection.id = 'writers';
    expect(state.access(second.id)).toBe('read_write');
    expect(state.selectedGroupDirty).toBe(true);
    state.dispose();
  });

  test('partial failure acknowledges successful namespaces and retries only remaining drafts', async (): Promise<void> => {
    const { state, api, initial, memory } = await createFixture();
    const second = await memory.create({ name: 'Archives', groups: [] });
    const third = await memory.create({ name: 'Final', groups: [] });
    await state.load();
    const update = vi.fn(memory.update).mockImplementationOnce(memory.update).mockRejectedValueOnce(new Error('Unavailable'));
    api.update = update;
    state.stageAccess(initial.id, 'none');
    state.stageAccess(second.id, 'read');
    state.stageAccess(third.id, 'read_write');
    await state.savePermissions();
    expect(update).toHaveBeenCalledTimes(2);
    expect(state.namespaces.find((entry) => entry.id === initial.id)?.revision).toBe(2);
    expect(state.permissionFeedback.message).toContain('1 namespace permission changes saved');
    expect(state.selectedGroupDirty).toBe(true);
    await state.savePermissions();
    expect(update.mock.calls.map(([id]) => id)).toEqual([initial.id, second.id, second.id, third.id]);
    expect(state.hasUnsavedChanges).toBe(false);
    expect(state.permissionFeedback.message).toBe('All changes saved');
    state.dispose();
  });

  test('metadata creates and edits never publish permission drafts and own metadata writes advance their known baseline', async (): Promise<void> => {
    const { state, initial, memory } = await createFixture();
    state.stageAccess(initial.id, 'none');
    state.beginCreate();
    state.changeName('New');
    await state.save();
    expect((await memory.list()).find((entry) => entry.name === 'New')?.groups).toEqual([]);
    expect(state.selectedGroupDirty).toBe(true);
    state.beginEdit(initial.id);
    state.changeName('Renamed');
    state.changeDescription('Description');
    await state.save();
    expect((await memory.list()).find((entry) => entry.id === initial.id)?.groups).toEqual(initial.groups);
    expect(state.access(initial.id)).toBe('none');
    await state.savePermissions();
    expect(state.needsReload).toBe(false);
    expect(state.namespaces.find((entry) => entry.id === initial.id)).toMatchObject({ name: 'Renamed', description: 'Description', revision: 3, groups: [{ group_id: 'writers', access: 'read_write' }] });
    state.dispose();
  });

  test('metadata conflict refresh and subsequent own save cannot rebase an older permission draft', async (): Promise<void> => {
    const { state, initial, memory, api } = await createFixture();
    state.stageAccess(initial.id, 'none');
    await memory.update(initial.id, { name: initial.name, groups: [{ group_id: 'readers', access: 'read_write' }], expected_revision: 1 });
    state.beginEdit(initial.id);
    state.changeName('My name');
    await state.save();
    expect(state.conflict).toBe(true);
    await state.refreshConflict();
    await state.save();
    expect(state.selectedGroupDirty).toBe(true);
    const update = vi.fn(memory.update);
    api.update = update;
    await state.savePermissions();
    expect(update).toHaveBeenCalledExactlyOnceWith(initial.id, { name: 'My name', groups: [], expected_revision: 1 });
    expect(state.needsReload).toBe(true);
    expect(state.permissionFeedback.message).toContain('Reload and review');
    await state.savePermissions();
    expect(update).toHaveBeenCalledTimes(1);
    expect((await memory.list())[0].groups).toEqual([{ group_id: 'readers', access: 'read_write' }]);
    state.dispose();
  });

  test('reload requires discard confirmation and cancellation retains the permission draft', async (): Promise<void> => {
    const { state, initial, api, memory } = await createFixture();
    const list = vi.fn(memory.list);
    api.list = list;
    state.stageAccess(initial.id, 'none');
    state.requestReload();
    expect(state.reloadConfirmation).toBe(true);
    expect(list).not.toHaveBeenCalled();
    state.resolveReload('cancel');
    expect(state.reloadConfirmation).toBe(false);
    expect(state.access(initial.id)).toBe('none');
    state.requestReload();
    state.resolveReload('discard');
    await vi.waitFor(() => expect(state.busy).toBe(false));
    expect(list).toHaveBeenCalledTimes(1);
    expect(state.hasUnsavedChanges).toBe(false);
    expect(state.access(initial.id)).toBe('read');
    state.dispose();
  });

  test.each(['identity', 'dispose'] as const)('%s replacement stops subsequent queued writes after an obsolete outcome', async (replacement): Promise<void> => {
    const { state, initial, api, memory } = await createFixture();
    const second = await memory.create({ name: 'Queued', groups: [] });
    await state.load();
    state.observeAccountIdentity({ kind: 'hidden' });
    const pending = deferred<SharedNamespace>();
    const update = vi.fn(() => pending.promise);
    api.update = update;
    state.stageAccess(initial.id, 'none');
    state.stageAccess(second.id, 'read');
    const saving = state.savePermissions();
    await state.savePermissions();
    expect(update).toHaveBeenCalledTimes(1);
    expect(state.permissionFeedback.tone).toBe('saving');
    if (replacement === 'dispose') state.dispose();
    else {
      const identity = await resolveWorkspaceAccess(new InMemoryWorkspaceApi({ identity_key: 'new', user: { id: 'new', name: 'Administrator', email: null, picture: null }, capabilities: { administration: true } }));
      state.observeAccountIdentity(identity.accountIdentity);
      await vi.waitFor(() => expect(state.busy).toBe(false));
    }
    pending.resolve({ ...initial, revision: 2, groups: [] });
    await saving;
    expect(update).toHaveBeenCalledTimes(1);
    expect(state.hasUnsavedChanges).toBe(false);
    state.dispose();
  });
});

describe('shared namespace operation lifetimes', () => {
  test('load closes the editor, blocks operations while pending and reports load failures outside it', async (): Promise<void> => {
    const { state, api, initial } = await createFixture();
    const pending = deferred<SharedNamespace[]>();
    api.list = () => pending.promise;
    state.beginEdit(initial.id);
    state.changeName('Discarded');
    const loading = state.load();
    expect(state.editorOpen).toBe(false);
    expect(state.name).toBe('');
    expect(state.busy).toBe(true);
    state.beginCreate();
    state.beginEdit(initial.id);
    state.stageAccess(initial.id, 'none');
    await state.savePermissions();
    expect(state.editorOpen).toBe(false);
    expect(state.canAssignAccess).toBe(false);
    pending.reject(new Error('Unavailable'));
    await loading;
    expect(state.busy).toBe(false);
    expect(state.error).toBe('Could not load shared namespaces.');
    state.beginCreate();
    expect(state.error).toBe('');
    state.dispose();
  });

  test('newer loads fence obsolete inventory and revision-refresh responses', async (): Promise<void> => {
    const { state, api, memory, initial } = await createFixture();
    const stale = deferred<SharedNamespace[]>();
    api.list = () => stale.promise;
    const first = state.load();
    api.list = memory.list;
    await state.load();
    stale.resolve([]);
    await first;
    expect(state.namespaces).toEqual([initial]);
    state.beginEdit(initial.id);
    state.changeName('Draft');
    const concurrent = await memory.update(initial.id, { name: 'Concurrent', expected_revision: 1, groups: [] });
    await state.save();
    const refresh = deferred<SharedNamespace[]>();
    api.list = () => refresh.promise;
    const refreshing = state.refreshConflict();
    api.list = memory.list;
    await state.load();
    refresh.resolve([initial]);
    await refreshing;
    expect(state.namespaces).toEqual([concurrent]);
    expect(state.editorOpen).toBe(false);
    expect(state.name).toBe('');
    expect(state.conflict).toBe(false);
    state.dispose();
  });

  test.each(['name', 'access'] as const)('identity replacement fences obsolete %s saves without altering the new draft', async (operation): Promise<void> => {
    const { state, api, initial } = await createFixture();
    const user = { id: 'same-subject', name: 'Administrator', email: null, picture: null };
    const accountA = await resolveWorkspaceAccess(new InMemoryWorkspaceApi({ identity_key: 'opaque-key-a', user, capabilities: { administration: true } }));
    const accountB = await resolveWorkspaceAccess(new InMemoryWorkspaceApi({ identity_key: 'opaque-key-b', user, capabilities: { administration: true } }));
    state.observeAccountIdentity(accountA.accountIdentity);
    const pending = deferred<SharedNamespace>();
    api.update = () => pending.promise;
    if (operation === 'name') {
      state.beginEdit(initial.id);
      state.changeName('Old draft');
      state.changeDescription('Old description');
    }
    if (operation === 'access') state.stageAccess(initial.id, 'none');
    const saving = operation === 'name' ? state.save() : state.savePermissions();
    api.list = async (): Promise<SharedNamespace[]> => [];
    state.observeAccountIdentity(accountB.accountIdentity);
    expect(state.editorOpen).toBe(false);
    expect(state.name).toBe('');
    expect(state.namespaces).toEqual([]);
    await vi.waitFor(() => expect(state.busy).toBe(false));
    state.beginCreate();
    state.changeName('Current draft');
    state.changeDescription('Current description');
    pending.resolve({ ...initial, name: 'Obsolete', revision: 2 });
    await saving;
    expect(state.namespaces).toEqual([]);
    expect(state.editorOpen).toBe(true);
    expect(state.name).toBe('Current draft');
    expect(state.description).toBe('Current description');
    state.dispose();
  });

  test.each(['name', 'access'] as const)('reload and disposal fence obsolete %s saves and prevent further work', async (operation): Promise<void> => {
    const { state, api, initial, memory } = await createFixture();
    const pending = deferred<SharedNamespace>();
    api.update = () => pending.promise;
    if (operation === 'name') state.beginEdit(initial.id);
    if (operation === 'access') state.stageAccess(initial.id, 'none');
    const saving = operation === 'name' ? state.save() : state.savePermissions();
    await state.load();
    pending.resolve({ ...initial, name: 'Obsolete', revision: 2 });
    await saving;
    expect(state.namespaces).toEqual([initial]);
    expect(state.editorOpen).toBe(false);
    const disposedPending = deferred<SharedNamespace>();
    api.update = () => disposedPending.promise;
    if (operation === 'name') state.beginEdit(initial.id);
    if (operation === 'access') state.stageAccess(initial.id, 'none');
    const disposedSaving = operation === 'name' ? state.save() : state.savePermissions();
    state.dispose();
    state.beginCreate();
    state.beginEdit(initial.id);
    state.changeName('Ignored');
    state.changeDescription('Ignored description');
    api.update = vi.fn(memory.update);
    await state.load();
    await state.save();
    state.stageAccess(initial.id, 'none');
    await state.savePermissions();
    disposedPending.reject(new HttpError(409, 'Obsolete conflict', {}));
    await disposedSaving;
    expect(api.update).not.toHaveBeenCalled();
    expect(state.namespaces).toEqual([]);
    expect(state.editorOpen).toBe(false);
    expect(state.name).toBe('');
    expect(state.error).toBe('');
    expect(state.conflict).toBe(false);
    expect(state.canSave).toBe(false);
    expect(state.canAssignAccess).toBe(false);
    expect(state.description).toBe('');
    expect(state.busy).toBe(false);
  });
});
