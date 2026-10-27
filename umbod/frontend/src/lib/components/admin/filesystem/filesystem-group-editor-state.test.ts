import { describe, expect, it } from 'vitest';
import { InMemoryFilesystemAdministration } from '$lib/admin/filesystem/in-memory';
import { rootPolicy } from '$lib/admin/filesystem/fixtures.test-support';
import { InMemoryGroupCatalogue } from '$lib/admin/groups/in-memory';
import { FilesystemAccessState } from './filesystem-access-state.svelte';
import { FilesystemGroupEditorState } from './filesystem-group-editor-state.svelte';
import { GroupRegistrationState } from '../group-permissions/shared/group-registration-state.svelte';

describe('inline filesystem group permissions', () => {
  it('stages multiple groups across selections and persists the whole projection', async (): Promise<void> => {
    const api = new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', groups: [{ group_id: 'readers', permissions: ['read'] }] }));
    const access = new FilesystemAccessState(api, new InMemoryGroupCatalogue([{ group_id: 'readers' }, { group_id: ' exact creators ' }]));
    await access.load();
    const editor = new FilesystemGroupEditorState(() => access);
    editor.toggle('share', true);
    editor.select(' exact creators ');
    editor.toggle('write', true);
    editor.select('readers');
    expect(editor.permissions).toEqual(['read', 'share']);
    expect((await api.getRootAccess()).groups).toEqual([{ group_id: 'readers', permissions: ['read'] }]);
    await access.save();
    expect((await api.getRootAccess()).groups).toEqual([
      { group_id: 'readers', permissions: ['read', 'share'] },
      { group_id: ' exact creators ', permissions: ['write'] }
    ]);
    expect(access.dirty).toBe(false);
    editor.select(' exact creators ');
    editor.toggle('write', false);
    expect(editor.selected?.group_id).toBe(' exact creators ');
    expect(editor.permissions).toEqual([]);
    await access.save();
    await access.load();
    expect(editor.selected?.group_id).toBe(' exact creators ');
    expect(editor.permissions).toEqual([]);
  });
  it('keeps saved unregistered groups selected until clearing is saved or discarded', async (): Promise<void> => {
    const api = new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', groups: [{ group_id: 'unregistered', permissions: ['read'] }] }));
    const access = new FilesystemAccessState(api, new InMemoryGroupCatalogue([{ group_id: 'other' }]));
    await access.load();
    const editor = new FilesystemGroupEditorState(() => access);
    editor.select('unregistered');
    editor.toggle('read', false);
    expect(editor.selected?.group_id).toBe('unregistered');
    expect(editor.permissions).toEqual([]);
    editor.toggle('share', true);
    expect(access.groups).toEqual([{ group_id: 'unregistered', permissions: ['share'] }]);
    access.requestReload();
    await access.confirm();
    expect(editor.permissions).toEqual(['read']);
    editor.toggle('read', false);
    await access.save();
    expect(access.confirmation).toBe('empty');
    await access.confirm();
    expect((await api.getRootAccess()).groups).toEqual([]);
    expect(access.groupEntries.map((group) => group.group_id)).toEqual(['other']);
  });
  it('disables blocked assignment while allowing other group edits', async (): Promise<void> => {
    const access = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({ blocked_group_ids: ['blocked'] })), new InMemoryGroupCatalogue([{ group_id: 'other' }]));
    await access.load();
    const editor = new FilesystemGroupEditorState(() => access);
    editor.select('blocked');
    expect(editor.editable).toBe(false);
    expect(editor.assignmentMessage).toContain('managed outside this editor');
    editor.toggle('read', true);
    expect(access.groups).toEqual([]);
    editor.select('other');
    expect(editor.editable).toBe(true);
    editor.toggle('read', true);
    expect(access.groups).toEqual([{ group_id: 'other', permissions: ['read'] }]);
  });
  it('registers independently without losing staged permissions or granting new access', async (): Promise<void> => {
    const api = new InMemoryFilesystemAdministration(rootPolicy());
    const catalogue = new InMemoryGroupCatalogue([{ group_id: 'existing' }]);
    const access = new FilesystemAccessState(api, catalogue);
    await access.load();
    const editor = new FilesystemGroupEditorState(() => access);
    editor.toggle('read', true);
    const draft = access.groups;
    const registration = new GroupRegistrationState(access.registerGroup, editor.select);
    registration.show();
    registration.edit('cancelled');
    registration.cancel();
    expect(access.groups).toEqual(draft);
    registration.show();
    registration.edit(' exact new group ');
    await registration.submit();
    expect(await catalogue.list()).toContainEqual({ group_id: ' exact new group ' });
    expect(editor.selected?.group_id).toBe(' exact new group ');
    expect(editor.permissions).toEqual([]);
    expect(access.groups).toEqual(draft);
    expect((await api.getRootAccess()).groups).toEqual([]);
    access.requestReload();
    await access.confirm();
    expect(access.dirty).toBe(false);
    expect(await catalogue.list()).toContainEqual({ group_id: ' exact new group ' });
  });
  it('keeps registration failures separate from permission drafts', async (): Promise<void> => {
    const registration = new GroupRegistrationState(async (): Promise<void> => { throw new Error('Failure'); }, (): void => {});
    registration.show();
    registration.edit(' ');
    expect(registration.valid).toBe(false);
    registration.edit('valid');
    await registration.submit();
    expect(registration.open).toBe(true);
    expect(registration.pending).toBe(false);
    expect(registration.error).toContain('could not be registered');
  });
});
